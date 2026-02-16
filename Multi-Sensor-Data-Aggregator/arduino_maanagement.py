#!/usr/bin/env python3
"""
Raspberry Pi IoT Management System
Handles Arduino sensor data collection, storage, and management
Compatible with AlmaLinux
"""

import serial
import sqlite3
import json
import time
import threading
import logging
import argparse
import signal
import sys
import os
from datetime import datetime, timedelta
from collections import deque
from typing import Dict, List, Tuple, Optional
import configparser
from pathlib import Path

# Configuration Management
class ConfigManager:
    def __init__(self, config_file='iot_config.ini'):
        self.config_file = config_file
        self.config = configparser.ConfigParser(inline_comment_prefixes=('#',))
        self.load_or_create_config()
    
    def load_or_create_config(self):
        if os.path.exists(self.config_file):
            self.config.read(self.config_file)
        else:
            self.create_default_config()
    
    def create_default_config(self):
        self.config['SERIAL'] = {
            'port': '/dev/ttyUSB0',
            'baudrate': '115200',
            'timeout': '1'
        }
        
        self.config['DATABASE'] = {
            'path': 'iot_sensors.db',
            'retention_days': '30',
            'backup_enabled': 'true',
            'backup_interval_hours': '24'
        }
        
        self.config['MONITORING'] = {
            'sensor_read_interval': '2000',
            'heartbeat_timeout': '30',
            'auto_reconnect': 'true',
            'max_reconnect_attempts': '10'
        }
        
        self.config['ALERTS'] = {
            'enabled': 'true',
            'temp_min': '-10',
            'temp_max': '50',
            'humidity_min': '20',
            'humidity_max': '80',
            'distance_min': '5',
            'distance_max': '200',
            'motion_threshold': '1' # 1 for motion detected
        }
        
        self.config['LOGGING'] = {
            'level': 'INFO',
            'file': 'iot_system.log',
            'max_size_mb': '100',
            'backup_count': '5'
        }
        
        self.config['API'] = {
            'enabled': 'false',
            'host': '0.0.0.0',
            'port': '8080'
        }
        
        self.save_config()
    
    def save_config(self):
        with open(self.config_file, 'w') as f:
            self.config.write(f)
    
    def get(self, section, key, fallback=None):
        try:
            return self.config.get(section, key)
        except:
            return fallback
    
    def getint(self, section, key, fallback=0):
        try:
            return self.config.getint(section, key)
        except:
            return fallback
    
    def getboolean(self, section, key, fallback=False):
        try:
            return self.config.getboolean(section, key)
        except:
            return fallback
    
    def set(self, section, key, value):
        if section not in self.config:
            self.config[section] = {}
        self.config[section][key] = str(value)
        self.save_config()

# Database Manager
class DatabaseManager:
    def __init__(self, config: ConfigManager):
        self.config = config
        self.db_path = config.get('DATABASE', 'path', 'iot_sensors.db')
        self.conn = None
        self.init_database()
    
    def init_database(self):
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.create_tables()
    
    def create_tables(self):
        cursor = self.conn.cursor()
        
        # Sensor inventory table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sensors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sensor_id TEXT UNIQUE NOT NULL,
                sensor_type TEXT,
                pin INTEGER,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                active BOOLEAN DEFAULT 1,
                metadata TEXT
            )
        ''')
        
        # Sensor data table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sensor_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sensor_id TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                value1 REAL,
                value2 REAL,
                value3 REAL,
                unit1 TEXT,
                unit2 TEXT,
                unit3 TEXT,
                raw_data TEXT,
                FOREIGN KEY (sensor_id) REFERENCES sensors(sensor_id)
            )
        ''')
        
        # System events table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                event_type TEXT,
                severity TEXT,
                message TEXT,
                data TEXT
            )
        ''')
        
        # Alerts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sensor_id TEXT,
                alert_type TEXT,
                value REAL,
                threshold REAL,
                message TEXT,
                acknowledged BOOLEAN DEFAULT 0
            )
        ''')
        
        # Statistics table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sensor_id TEXT,
                date DATE,
                min_value REAL,
                max_value REAL,
                avg_value REAL,
                count INTEGER,
                UNIQUE(sensor_id, date)
            )
        ''')
        
        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sensor_data_timestamp ON sensor_data(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sensor_data_sensor_id ON sensor_data(sensor_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)')
        
        self.conn.commit()
    
    def add_sensor(self, sensor_id: str, sensor_type: str, pin: int, metadata: dict = None):
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO sensors (sensor_id, sensor_type, pin, metadata, last_seen)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (sensor_id, sensor_type, pin, json.dumps(metadata) if metadata else None))
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error adding sensor: {e}")
    
    def add_sensor_data(self, sensor_id: str, values: list, units: list, raw_data: str = None):
        cursor = self.conn.cursor()
        try:
            # Pad lists to ensure we have 3 values
            values = (values + [None, None, None])[:3]
            units = (units + [None, None, None])[:3]
            
            cursor.execute('''
                INSERT INTO sensor_data 
                (sensor_id, value1, value2, value3, unit1, unit2, unit3, raw_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (sensor_id, *values, *units, raw_data))
            
            # Update last_seen
            cursor.execute('''
                UPDATE sensors SET last_seen = CURRENT_TIMESTAMP WHERE sensor_id = ?
            ''', (sensor_id,))
            
            self.conn.commit()
            
            # Check alerts
            self.check_alerts(sensor_id, values[0] if values[0] is not None else 0)
            
        except Exception as e:
            logging.error(f"Error adding sensor data: {e}")
    
    def check_alerts(self, sensor_id: str, value: float):
        alerts_config = self.config.config['ALERTS']
        if not self.config.getboolean('ALERTS', 'enabled'):
            return
        
        cursor = self.conn.cursor()
        alert_triggered = False
        alert_type = ""
        threshold = 0
        
        # Check temperature alerts
        if 'temp' in sensor_id.lower() or 'dht' in sensor_id.lower() or 'bmp' in sensor_id.lower():
            temp_min = float(alerts_config.get('temp_min', -10))
            temp_max = float(alerts_config.get('temp_max', 50))
            
            if value < temp_min:
                alert_triggered = True
                alert_type = "LOW_TEMPERATURE"
                threshold = temp_min
            elif value > temp_max:
                alert_triggered = True
                alert_type = "HIGH_TEMPERATURE"
                threshold = temp_max
        
        # Check distance alerts
        elif 'hc-sr04' in sensor_id.lower() or 'ultrasonic' in sensor_id.lower():
            dist_min = float(alerts_config.get('distance_min', 5))
            dist_max = float(alerts_config.get('distance_max', 200))
            
            if value < dist_min:
                alert_triggered = True
                alert_type = "PROXIMITY_ALERT"
                threshold = dist_min
            elif value > dist_max:
                alert_triggered = True
                alert_type = "DISTANCE_EXCEEDED"
                threshold = dist_max
        
        # Check PIR alerts
        elif 'pir' in sensor_id.lower():
            motion_threshold = float(alerts_config.get('motion_threshold', 1))
            if value >= motion_threshold:
                alert_triggered = True
                alert_type = "MOTION_DETECTED"
                threshold = motion_threshold
        
        if alert_triggered:
            message = f"Sensor {sensor_id}: {alert_type} - Value {value:.2f} exceeds threshold {threshold:.2f}"
            cursor.execute('''
                INSERT INTO alerts (sensor_id, alert_type, value, threshold, message)
                VALUES (?, ?, ?, ?, ?)
            ''', (sensor_id, alert_type, value, threshold, message))
            self.conn.commit()
            logging.warning(message)
    
    def add_event(self, event_type: str, severity: str, message: str, data: dict = None):
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO events (event_type, severity, message, data)
                VALUES (?, ?, ?, ?)
            ''', (event_type, severity, message, json.dumps(data) if data else None))
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error adding event: {e}")
    
    def get_latest_readings(self, limit: int = 100) -> list:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT sensor_id, timestamp, value1, value2, value3, unit1, unit2, unit3
            FROM sensor_data
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (limit,))
        return cursor.fetchall()
    
    def get_sensor_statistics(self, sensor_id: str, days: int = 7) -> dict:
        cursor = self.conn.cursor()
        since = datetime.now() - timedelta(days=days)
        
        cursor.execute('''
            SELECT 
                MIN(value1) as min_val,
                MAX(value1) as max_val,
                AVG(value1) as avg_val,
                COUNT(*) as count
            FROM sensor_data
            WHERE sensor_id = ? AND timestamp > ?
        ''', (sensor_id, since))
        
        result = cursor.fetchone()
        return {
            'min': result[0],
            'max': result[1],
            'avg': result[2],
            'count': result[3]
        }
    
    def cleanup_old_data(self):
        retention_days = self.config.getint('DATABASE', 'retention_days', 30)
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM sensor_data WHERE timestamp < ?', (cutoff_date,))
        cursor.execute('DELETE FROM events WHERE timestamp < ?', (cutoff_date,))
        deleted = cursor.rowcount
        self.conn.commit()
        
        if deleted > 0:
            logging.info(f"Cleaned up {deleted} old records")
        
        # Vacuum database to reclaim space
        cursor.execute('VACUUM')
    
    def backup_database(self):
        if not self.config.getboolean('DATABASE', 'backup_enabled'):
            return
        
        backup_path = f"{self.db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        try:
            backup_conn = sqlite3.connect(backup_path)
            self.conn.backup(backup_conn)
            backup_conn.close()
            logging.info(f"Database backed up to {backup_path}")
            
            # Keep only last 5 backups
            self.cleanup_old_backups()
        except Exception as e:
            logging.error(f"Backup failed: {e}")
    
    def cleanup_old_backups(self):
        backup_files = sorted(Path('.').glob(f"{self.db_path}.backup_*"))
        if len(backup_files) > 5:
            for old_backup in backup_files[:-5]:
                old_backup.unlink()
                logging.info(f"Deleted old backup: {old_backup}")
    
    def close(self):
        if self.conn:
            self.conn.close()

# Serial Communication Manager
class SerialManager:
    def __init__(self, config: ConfigManager, db: DatabaseManager):
        self.config = config
        self.db = db
        self.port = config.get('SERIAL', 'port', '/dev/ttyUSB0')
        self.baudrate = config.getint('SERIAL', 'baudrate', 115200)
        self.timeout = config.getint('SERIAL', 'timeout', 1)
        self.serial_conn = None
        self.running = False
        self.read_thread = None
        self.last_heartbeat = time.time()
        self.sensor_inventory = {}
        self.message_queue = deque(maxlen=100)
        
    def connect(self) -> bool:
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout
            )
            time.sleep(2)  # Wait for Arduino to reset
            logging.info(f"Connected to Arduino on {self.port}")
            self.db.add_event("SERIAL", "INFO", f"Connected to {self.port}")
            return True
        except Exception as e:
            logging.error(f"Failed to connect: {e}")
            self.db.add_event("SERIAL", "ERROR", f"Connection failed: {e}")
            return False
    
    def start(self):
        if not self.serial_conn:
            if not self.connect():
                return False
        
        self.running = True
        self.read_thread = threading.Thread(target=self.read_loop, daemon=True)
        self.read_thread.start()
        
        # Request initial status
        time.sleep(0.5)
        self.send_command("STATUS")
        
        return True
    
    def read_loop(self):
        buffer = ""
        
        while self.running:
            try:
                if self.serial_conn and self.serial_conn.in_waiting:
                    data = self.serial_conn.read(self.serial_conn.in_waiting).decode('utf-8', errors='ignore')
                    buffer += data
                    
                    # Process complete messages
                    while '<' in buffer and '>' in buffer:
                        start = buffer.index('<')
                        end = buffer.index('>', start)
                        message = buffer[start+1:end]
                        buffer = buffer[end+1:]
                        self.process_message(message)
                
                # Check heartbeat timeout
                if time.time() - self.last_heartbeat > self.config.getint('MONITORING', 'heartbeat_timeout', 30):
                    logging.warning("Heartbeat timeout - Arduino may be disconnected")
                    self.db.add_event("HEARTBEAT", "WARNING", "Heartbeat timeout")
                    
                    if self.config.getboolean('MONITORING', 'auto_reconnect'):
                        self.reconnect()
                
                time.sleep(0.01)
                
            except Exception as e:
                logging.error(f"Read error: {e}")
                if self.config.getboolean('MONITORING', 'auto_reconnect'):
                    self.reconnect()
                time.sleep(1)
    
    def process_message(self, message: str):
        try:
            parts = message.split('|')
            if len(parts) < 3:
                return
            
            msg_type = parts[0]
            timestamp = parts[1]
            content = '|'.join(parts[2:])
            
            # Store message
            self.message_queue.append({
                'type': msg_type,
                'timestamp': timestamp,
                'content': content,
                'received': datetime.now()
            })
            
            # Process by type
            if msg_type == "DATA":
                self.process_data(content)
            elif msg_type == "INVENTORY":
                self.process_inventory(content)
            elif msg_type == "HEARTBEAT":
                self.process_heartbeat(content)
            elif msg_type == "STATUS" or msg_type == "BOOT":
                logging.info(f"Arduino: {content}")
                self.db.add_event("ARDUINO", "INFO", content)
            elif msg_type == "DETECT":
                logging.info(f"Detection result: {content}")
                
        except Exception as e:
            logging.error(f"Error processing message: {e}")
    
    def process_data(self, content: str):
        try:
            parts = content.split(',')
            if len(parts) < 2:
                return
            
            sensor_id = parts[0]
            values = []
            units = []
            
            # Parse values and units
            for i in range(1, len(parts)):
                try:
                    val = float(parts[i])
                    values.append(val)
                except:
                    # It's a unit string
                    units.append(parts[i])
            
            # Store in database
            self.db.add_sensor_data(sensor_id, values, units, content)
            
            # Log if debug mode
            if self.config.get('LOGGING', 'level') == 'DEBUG':
                logging.debug(f"Data from {sensor_id}: {values} {units}")
                
        except Exception as e:
            logging.error(f"Error processing data: {e}")
    
    def process_inventory(self, content: str):
        try:
            parts = content.split('|')
            count = int(parts[0])
            
            if len(parts) > 1:
                sensors = parts[1].split(',')
                for sensor in sensors:
                    if ':' in sensor:
                        sensor_id, sensor_type = sensor.split(':')
                        self.sensor_inventory[sensor_id] = sensor_type # Store as string
                        
                        # Update database
                        self.db.add_sensor(sensor_id, sensor_type, 0)
            
            logging.info(f"Sensor inventory updated: {count} sensors")
            self.db.add_event("INVENTORY", "INFO", f"Updated: {count} sensors", self.sensor_inventory)
            
        except Exception as e:
            logging.error(f"Error processing inventory: {e}")
    
    def process_heartbeat(self, content: str):
        self.last_heartbeat = time.time()
        parts = content.split('|')
        status = parts[0] if parts else "UNKNOWN"
        
        if status != "OK":
            logging.warning(f"Arduino status: {status}")
            self.db.add_event("HEARTBEAT", "WARNING", f"Status: {status}")
    
    def send_command(self, command: str, *args):
        if not self.serial_conn:
            return False
        
        try:
            message = f"<{command}"
            for arg in args:
                message += f"|{arg}"
            message += ">"
            
            self.serial_conn.write(message.encode())
            logging.debug(f"Sent command: {message}")
            return True
            
        except Exception as e:
            logging.error(f"Error sending command: {e}")
            return False
    
    def reconnect(self):
        logging.info("Attempting to reconnect...")
        max_attempts = self.config.getint('MONITORING', 'max_reconnect_attempts', 10)
        
        for attempt in range(max_attempts):
            if self.serial_conn:
                self.serial_conn.close()
                self.serial_conn = None
            
            time.sleep(2)
            
            if self.connect():
                logging.info(f"Reconnected after {attempt + 1} attempts")
                self.db.add_event("SERIAL", "INFO", f"Reconnected after {attempt + 1} attempts")
                return True
            
            time.sleep(5)
        
        logging.error("Failed to reconnect")
        self.db.add_event("SERIAL", "ERROR", "Reconnection failed")
        return False
    
    def stop(self):
        self.running = False
        if self.read_thread:
            self.read_thread.join(timeout=2)
        if self.serial_conn:
            self.serial_conn.close()

# Main IoT Manager
class IoTManager:
    def __init__(self, config_file='iot_config.ini'):
        self.config = ConfigManager(config_file)
        self.setup_logging()
        self.db = DatabaseManager(self.config)
        self.serial = SerialManager(self.config, self.db)
        self.running = False
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def setup_logging(self):
        level = getattr(logging, self.config.get('LOGGING', 'level', 'INFO'))
        log_file = self.config.get('LOGGING', 'file', 'iot_system.log')
        
        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
    
    def signal_handler(self, signum, frame):
        logging.info("Shutdown signal received")
        self.stop()
        sys.exit(0)
    
    def start(self):
        logging.info("Starting IoT Management System")
        self.db.add_event("SYSTEM", "INFO", "System started")
        
        self.running = True
        
        # Start serial communication
        if not self.serial.start():
            logging.error("Failed to start serial communication")
            return False
        
        # Start maintenance thread
        maintenance_thread = threading.Thread(target=self.maintenance_loop, daemon=True)
        maintenance_thread.start()
        
        # Start monitoring thread
        monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        monitor_thread.start()
        
        return True
    
    def maintenance_loop(self):
        last_cleanup = time.time()
        last_backup = time.time()
        
        while self.running:
            current_time = time.time()
            
            # Daily cleanup
            if current_time - last_cleanup > 86400:  # 24 hours
                logging.info("Running database cleanup")
                self.db.cleanup_old_data()
                last_cleanup = current_time
            
            # Backup
            backup_interval = self.config.getint('DATABASE', 'backup_interval_hours', 24) * 3600
            if current_time - last_backup > backup_interval:
                logging.info("Running database backup")
                self.db.backup_database()
                last_backup = current_time
            
            time.sleep(60)  # Check every minute
    
    def monitor_loop(self):
        while self.running:
            try:
                # Get latest readings for monitoring
                readings = self.db.get_latest_readings(10)
                
                # Check for stale sensors
                cursor = self.db.conn.cursor()
                cursor.execute('''
                    SELECT sensor_id, last_seen FROM sensors
                    WHERE active = 1 AND last_seen < datetime('now', '-5 minutes')
                ''')
                stale_sensors = cursor.fetchall()
                
                for sensor_id, last_seen in stale_sensors:
                    logging.warning(f"Sensor {sensor_id} hasn't reported since {last_seen}")
                    self.db.add_event("SENSOR", "WARNING", f"Sensor {sensor_id} is stale")
                
                # Update sensor read interval if changed
                interval = self.config.getint('MONITORING', 'sensor_read_interval', 2000)
                self.serial.send_command("CONFIG", "INTERVAL", str(interval))
                
            except Exception as e:
                logging.error(f"Monitor error: {e}")
            
            time.sleep(30)  # Check every 30 seconds
    
    def configure_arduino(self):
        """Send configuration to Arduino"""
        # Set read interval
        interval = self.config.getint('MONITORING', 'sensor_read_interval', 2000)
        self.serial.send_command("CONFIG", "INTERVAL", str(interval))
        
        # Enable/disable auto-detect
        auto_detect = "1" if self.config.getboolean('MONITORING', 'auto_detect', True) else "0"
        self.serial.send_command("CONFIG", "AUTODETECT", auto_detect)
        
        # Enable debug mode if needed
        debug = "1" if self.config.get('LOGGING', 'level') == 'DEBUG' else "0"
        self.serial.send_command("CONFIG", "DEBUG", debug)
    
    def run_cli(self):
        """Interactive CLI for management"""
        print("\n=== IoT Management System CLI ===")
        print("Commands: status, sensors, detect, config, stats, alerts, export, quit")
        
        while self.running:
            try:
                cmd = input("\n> ").strip().lower()
                
                if cmd == "quit" or cmd == "exit":
                    break
                elif cmd == "status":
                    self.show_status()
                elif cmd == "sensors":
                    self.show_sensors()
                elif cmd == "detect":
                    self.serial.send_command("DETECT")
                    print("Detection triggered")
                elif cmd == "config":
                    self.show_config()
                elif cmd == "stats":
                    self.show_statistics()
                elif cmd == "alerts":
                    self.show_alerts()
                elif cmd == "export":
                    self.export_data()
                elif cmd.startswith("set "):
                    self.set_config(cmd[4:])
                else:
                    print("Unknown command")
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}")
    
    def show_status(self):
        cursor = self.db.conn.cursor()
        
        # Count active sensors
        cursor.execute("SELECT COUNT(*) FROM sensors WHERE active = 1")
        active_sensors = cursor.fetchone()[0]
        
        # Count recent readings
        cursor.execute("SELECT COUNT(*) FROM sensor_data WHERE timestamp > datetime('now', '-1 hour')")
        recent_readings = cursor.fetchone()[0]
        
        # Count alerts
        cursor.execute("SELECT COUNT(*) FROM alerts WHERE acknowledged = 0")
        unack_alerts = cursor.fetchone()[0]
        
        print(f"\nSystem Status:")
        print(f"  Active Sensors: {active_sensors}")
        print(f"  Recent Readings (1h): {recent_readings}")
        print(f"  Unacknowledged Alerts: {unack_alerts}")
        print(f"  Serial Port: {self.serial.port}")
        print(f"  Last Heartbeat: {time.time() - self.serial.last_heartbeat:.1f}s ago")
    
    def show_sensors(self):
        cursor = self.db.conn.cursor()
        cursor.execute('''
            SELECT s.sensor_id, s.sensor_type, s.last_seen,
                   COUNT(d.id) as readings,
                   MAX(d.value1) as last_value
            FROM sensors s
            LEFT JOIN sensor_data d ON s.sensor_id = d.sensor_id
            WHERE s.active = 1
            GROUP BY s.sensor_id
        ''')
        
        sensors = cursor.fetchall()
        print(f"\nActive Sensors ({len(sensors)}):")
        print(f"{'ID':<15} {'Type':<8} {'Readings':<10} {'Last Value':<12} {'Last Seen'}")
        print("-" * 70)
        
        for sensor in sensors:
            sensor_id, sensor_type, last_seen, readings, last_value = sensor
            last_value_str = f"{last_value:.2f}" if last_value else "N/A"
            print(f"{sensor_id:<15} {sensor_type:<8} {readings:<10} {last_value_str:<12} {last_seen}")
    
    def show_config(self):
        print("\nCurrent Configuration:")
        for section in self.config.config.sections():
            print(f"\n[{section}]")
            for key, value in self.config.config[section].items():
                print(f"  {key}: {value}")
    
    def set_config(self, args):
        parts = args.split()
        if len(parts) != 3:
            print("Usage: set <section> <key> <value>")
            return
        
        section, key, value = parts
        self.config.set(section.upper(), key, value)
        print(f"Set {section}.{key} = {value}")
        
        # Apply certain configs immediately
        if section.upper() == "MONITORING" and key == "sensor_read_interval":
            self.serial.send_command("CONFIG", "INTERVAL", value)
    
    def show_statistics(self):
        cursor = self.db.conn.cursor()
        
        print("\nSensor Statistics (Last 7 Days):")
        cursor.execute("SELECT DISTINCT sensor_id FROM sensors WHERE active = 1")
        
        for (sensor_id,) in cursor.fetchall():
            stats = self.db.get_sensor_statistics(sensor_id, 7)
            if stats['count'] > 0:
                print(f"\n{sensor_id}:")
                print(f"  Readings: {stats['count']}")
                print(f"  Min: {stats['min']:.2f}")
                print(f"  Max: {stats['max']:.2f}")
                print(f"  Avg: {stats['avg']:.2f}")
    
    def show_alerts(self):
        cursor = self.db.conn.cursor()
        cursor.execute('''
            SELECT id, timestamp, sensor_id, alert_type, value, threshold, message
            FROM alerts
            WHERE acknowledged = 0
            ORDER BY timestamp DESC
            LIMIT 20
        ''')
        
        alerts = cursor.fetchall()
        print(f"\nUnacknowledged Alerts ({len(alerts)}):")
        
        for alert in alerts:
            alert_id, timestamp, sensor_id, alert_type, value, threshold, message = alert
            print(f"\n[{alert_id}] {timestamp}")
            print(f"  Sensor: {sensor_id}")
            print(f"  Type: {alert_type}")
            print(f"  Value: {value:.2f} (Threshold: {threshold:.2f})")
            print(f"  {message}")
    
    def export_data(self):
        filename = f"iot_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        cursor = self.db.conn.cursor()
        
        cursor.execute('''
            SELECT sensor_id, timestamp, value1, value2, value3, unit1, unit2, unit3
            FROM sensor_data
            ORDER BY timestamp DESC
        ''')
        
        with open(filename, 'w') as f:
            f.write("sensor_id,timestamp,value1,value2,value3,unit1,unit2,unit3\n")
            for row in cursor.fetchall():
                f.write(','.join(str(x) if x is not None else '' for x in row) + '\n')
        
        print(f"Data exported to {filename}")
    
    def stop(self):
        logging.info("Stopping IoT Management System")
        self.running = False
        self.serial.stop()
        self.db.add_event("SYSTEM", "INFO", "System stopped")
        self.db.close()

# Main entry point
def main():
    parser = argparse.ArgumentParser(description='IoT Management System for Raspberry Pi')
    parser.add_argument('--config', default='iot_config.ini', help='Configuration file path')
    parser.add_argument('--port', help='Serial port (overrides config)')
    parser.add_argument('--baudrate', type=int, help='Baud rate (overrides config)')
    parser.add_argument('--daemon', action='store_true', help='Run as daemon (no CLI)')
    parser.add_argument('--reset-db', action='store_true', help='Reset database')
    
    args = parser.parse_args()
    
    # Create manager
    manager = IoTManager(args.config)
    
    # Override settings if provided
    if args.port:
        manager.config.set('SERIAL', 'port', args.port)
    if args.baudrate:
        manager.config.set('SERIAL', 'baudrate', str(args.baudrate))
    
    # Reset database if requested
    if args.reset_db:
        if os.path.exists(manager.db.db_path):
            os.remove(manager.db.db_path)
            print(f"Database {manager.db.db_path} deleted")
        manager.db.init_database()
        print("Database reinitialized")
    
    # Start the system
    if not manager.start():
        print("Failed to start system")
        sys.exit(1)
    
    # Configure Arduino
    time.sleep(1)
    manager.configure_arduino()
    
    try:
        if args.daemon:
            print("Running in daemon mode. Press Ctrl+C to stop.")
            while True:
                time.sleep(1)
        else:
            # Run interactive CLI
            manager.run_cli()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        manager.stop()

if __name__ == "__main__":
    main()
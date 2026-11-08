#########################################################################
#                                                                       #
#   SECURE DRONE SWARM SYSTEM - CORE MODULE                             #
#                                                                       #
#   Developer : Md Shahanur Islam Shagor                                #
#   Role      : Project Architect & Lead Developer                      #
#   Version   : 1.0.2                                                   #
#   Status    : Production Ready                                        #
#                                                                       #
#   "Protecting the skies with decentralized intelligence."             #
#                                                                       #
#########################################################################
"""
Main Application Entry Point
Drone Swarm Management System
"""

import sys
import os
import logging
import argparse
import unittest
import random
from datetime import datetime

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'python'))

from drone import Drone, Position
from swarm_manager import SwarmManager
from communication import CommunicationManager
from ml_system import MLDecisionSupport, FormationController
from gui import start_gui

def setup_logging():
    """Setup logging configuration"""
    os.makedirs('logs', exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(f'logs/system_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
            logging.StreamHandler()
        ]
    )

def _load_runtime_config() -> dict:
    """
    Runtime real-drone settings from env.
    - REAL_DRONE_ENABLED=1
    - REAL_DRONE_CONNECTIONS=1=udpin://:14540,2=udpin://:14541
    - REAL_GPS_REF_LAT=23.8103
    - REAL_GPS_REF_LON=90.4125
    """
    enabled = os.getenv("REAL_DRONE_ENABLED", "0").strip().lower() in {"1", "true", "yes"}
    connections_raw = os.getenv("REAL_DRONE_CONNECTIONS", "").strip()
    connections = {}
    if connections_raw:
        for pair in connections_raw.split(","):
            if "=" not in pair:
                continue
            drone_id_text, conn = pair.split("=", 1)
            try:
                drone_id = int(drone_id_text.strip())
            except ValueError:
                continue
            conn = conn.strip()
            if conn:
                connections[drone_id] = conn

    cfg = {
        "real_drone_enabled": enabled,
        "connections": connections,
    }
    lat = os.getenv("REAL_GPS_REF_LAT")
    lon = os.getenv("REAL_GPS_REF_LON")
    if lat is not None and lon is not None:
        try:
            cfg["gps_reference"] = {"lat": float(lat), "lon": float(lon)}
        except ValueError:
            pass
    return cfg


def _load_dotenv_file(dotenv_path: str = ".env"):
    """Load .env key=value pairs into environment without overriding existing vars."""
    if not os.path.exists(dotenv_path):
        return
    try:
        with open(dotenv_path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception as e:
        logging.getLogger("Main").warning(f"Could not load .env file: {e}")

def create_demo_swarm():
    """Create a demonstration swarm"""
    swarm = SwarmManager()
    config = _load_runtime_config()
    real_enabled = bool(config.get("real_drone_enabled", False))
    per_drone_conn = config.get("connections", {})
    gps_ref = config.get("gps_reference", {})
    
    # Create 5 drones in a realistic, meter-based local world frame
    # (x=east meters, y=north meters). Spread remains within 10 km range.
    drone_positions = [
        Position(0, 0, 0),          # Drone 1
        Position(1200, 300, 0),     # Drone 2
        Position(-1400, -500, 0),   # Drone 3
        Position(800, -1500, 0),    # Drone 4
        Position(-900, 1600, 0)     # Drone 5
    ]
    
    for i, pos in enumerate(drone_positions, start=1):
        real_conn = per_drone_conn.get(i) if real_enabled else None
        drone = Drone(i, pos, real_drone_connection=real_conn)
        if "lat" in gps_ref and "lon" in gps_ref:
            drone.set_gps_reference(float(gps_ref["lat"]), float(gps_ref["lon"]))
        swarm.add_drone(drone)

    # Auto-populate dynamic obstacles so simulation starts with active traffic.
    auto_obstacles = random.randint(20, 30)
    swarm.populate_dynamic_obstacle_field(
        count=auto_obstacles,
        area_radius=2600.0,
    )
    
    return swarm

def main():
    """Main application entry"""
    parser = argparse.ArgumentParser(description="Drone Swarm Management System")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run test suite only and exit",
    )
    parser.add_argument(
        "--mesh-simulation",
        action="store_true",
        help="Run experimental quorum-controlled Drone simulation without real hardware or GUI",
    )
    parser.add_argument(
        "--mesh-gui",
        action="store_true",
        help="Open a simulation-only PyQt mesh coordination dashboard",
    )
    args = parser.parse_args()
    if sum(bool(x) for x in (args.test, args.mesh_simulation, args.mesh_gui)) > 1:
        parser.error("Choose exactly one execution mode")

    if args.mesh_gui:
        from swarm_dashboard import start_mesh_dashboard
        start_mesh_dashboard()
        return

    if args.mesh_simulation:
        if args.test:
            parser.error("--test and --mesh-simulation cannot be combined")
        from mesh_simulation import demo
        demo()
        return

    if args.test:
        suite = unittest.defaultTestLoader.discover(".", pattern="test*.py")
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        raise SystemExit(0 if result.wasSuccessful() else 1)

    print("=" * 60)
    print("DRONE SWARM MANAGEMENT SYSTEM")
    print("Secure and Fault-Tolerant Multi-Drone System")
    print("=" * 60)
    print()
    
    # Setup logging
    setup_logging()
    _load_dotenv_file(".env")
    logger = logging.getLogger("Main")
    
    logger.info("Starting Drone Swarm Management System")
    
    try:
        # Create swarm manager
        swarm_manager = create_demo_swarm()
        
        # Start swarm operations
        swarm_manager.start()
        
        logger.info(f"Swarm created with {len(swarm_manager.drones)} drones")
        logger.info(f"Leader elected: Drone {swarm_manager.leader_id}")
        
        # Start GUI
        logger.info("Starting GUI...")
        start_gui(swarm_manager)
        
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
    finally:
        # Cleanup
        if 'swarm_manager' in locals():
            swarm_manager.stop()
        logger.info("System shutdown complete")
        if 'swarm_manager' in locals():
            swarm_manager.finalize_runtime_graphs(force=True)

if __name__ == "__main__":
    main()

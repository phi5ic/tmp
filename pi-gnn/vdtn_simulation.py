from vdtn_node import VDTNNode

if __name__ == "__main__":
    # Simulate truck (FMCG transport) entering a dead zone
    truck = VDTNNode("Truck-FMCG-01", is_fleeing=False)
    truck.enter_dead_zone()
    print("-" * 50)
    
    # Simulate a fleeing vehicle coming from the flood zone
    fleeing_vehicle = VDTNNode("Fleeing-Vehicle-02", is_fleeing=True)
    # Fleeing vehicle experienced flash flood: y=1.2m, V=2.0m/s
    fleeing_vehicle.generate_telemetry("NH544-Chalakudy-Bridge", 1.2, 2.0)
    print("-" * 50)
    
    # They intercept each other
    truck.wifi_direct_handshake(fleeing_vehicle)
    print("-" * 50)
    
    # Truck's edge node instantaneously calculates hazard and reroutes
    truck.evaluate_route()

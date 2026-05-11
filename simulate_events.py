
## 3. Event Simulator Script

Create `simulate_events.py` for standalone event generation:

```python
import requests
import random
from datetime import datetime
import time
import json

# Configuration
WEBHOOK_URL = "http://localhost:5000/webhook"
NUM_EVENTS = 20
SLEEP_BETWEEN = 0.1  # seconds

# Event definitions
SOURCES = {
    'customer.io': ['email_opened', 'email_clicked', 'email_bounced', 'email_unsubscribed'],
    'appcues': ['tour_started', 'tour_completed', 'tour_dismissed', 'flow_completed'],
    'linkedin': ['ad_clicked', 'ad_impression', 'lead_converted', 'form_submitted']
}

CAMPAIGNS = [
    'onboarding_sequence',
    'product_tour',
    'linkedin_retargeting',
    'reengagement_campaign'
]

DOMAINS = ['company.com', 'startup.io', 'enterprise.org']

def generate_payload(source, event_type):
    """Generate a realistic webhook payload"""
    return {
        "source": source,
        "event_type": event_type,
        "campaign_name": random.choice(CAMPAIGNS),
        "user_email": f"user_{random.randint(1, 1000)}@{random.choice(DOMAINS)}",
        "timestamp": datetime.now().isoformat(),
        "metadata": {
            "ip": f"192.168.1.{random.randint(1, 255)}",
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            "session_id": f"ses_{random.randint(100000, 999999)}"
        }
    }

def simulate_normal_traffic():
    """Simulate normal event traffic"""
    print(f"🎮 Starting event simulation: {NUM_EVENTS} events")
    print(f"📡 Target: {WEBHOOK_URL}")
    print("-" * 50)
    
    success_count = 0
    error_count = 0
    
    for i in range(NUM_EVENTS):
        # Select random source and event
        source = random.choice(list(SOURCES.keys()))
        event_type = random.choice(SOURCES[source])
        
        # Generate payload
        payload = generate_payload(source, event_type)
        
        try:
            # Send webhook
            response = requests.post(
                WEBHOOK_URL,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=5
            )
            
            if response.status_code == 201:
                success_count += 1
                print(f"✅ Event {i+1}/{NUM_EVENTS}: {source}.{event_type} - Success")
            else:
                error_count += 1
                print(f"❌ Event {i+1}/{NUM_EVENTS}: {source}.{event_type} - Error {response.status_code}: {response.text}")
                
        except requests.exceptions.ConnectionError:
            print(f"❌ Event {i+1}/{NUM_EVENTS}: Connection failed - Is Flask running?")
            error_count += 1
        except Exception as e:
            print(f"❌ Event {i+1}/{NUM_EVENTS}: {str(e)}")
            error_count += 1
        
        time.sleep(SLEEP_BETWEEN)
    
    print("-" * 50)
    print(f"📊 Simulation complete: {success_count} successful, {error_count} failed")

def simulate_anomaly():
    """Simulate an anomaly - stop sending certain events"""
    print("⚠️  Simulating anomaly: Stopping email_opened events for 30 seconds")
    print("Check the dashboard for anomaly detection!")
    
    # Send normal events but skip email_opened
    for i in range(10):
        source = random.choice(['appcues', 'linkedin'])  # Skip customer.io
        event_type = random.choice(SOURCES[source])
        payload = generate_payload(source, event_type)
        
        try:
            response = requests.post(WEBHOOK_URL, json=payload, timeout=5)
            print(f"✅ Event {i+1}/10: {source}.{event_type}")
        except:
            print(f"❌ Failed to send event")
        
        time.sleep(1)

if __name__ == "__main__":
    print("=" * 50)
    print("Webhook Event Simulator")
    print("=" * 50)
    print("\n1. Normal Traffic Simulation")
    print("2. Anomaly Simulation")
    print("3. Custom Simulation")
    
    choice = input("\nSelect simulation type (1-3): ").strip()
    
    if choice == "1":
        simulate_normal_traffic()
    elif choice == "2":
        simulate_anomaly()
    elif choice == "3":
        custom_num = int(input("Number of events: "))
        NUM_EVENTS = custom_num
        simulate_normal_traffic()
    else:
        print("Invalid choice")
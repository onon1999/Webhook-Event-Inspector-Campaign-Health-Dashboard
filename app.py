import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import sqlite3
from flask import Flask, request, jsonify
import threading
import time
import os
import uuid

# ============================================
# DATABASE SETUP
# ============================================

def init_db():
    """Initialize SQLite database for storing webhook events"""
    conn = sqlite3.connect('webhook_events.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            source TEXT NOT NULL,
            event_type TEXT NOT NULL,
            campaign_name TEXT,
            user_email TEXT,
            metadata TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS anomaly_thresholds (
            id INTEGER PRIMARY KEY,
            event_type TEXT NOT NULL,
            campaign_name TEXT,
            min_expected INTEGER NOT NULL,
            time_window_hours INTEGER DEFAULT 1
        )
    ''')
    
    # Insert default thresholds if not exists
    cursor.execute('SELECT COUNT(*) FROM anomaly_thresholds')
    if cursor.fetchone()[0] == 0:
        default_thresholds = [
            ('email_opened', 'onboarding_sequence', 10, 1),
            ('email_clicked', 'onboarding_sequence', 5, 1),
            ('tour_completed', 'product_tour', 3, 1),
            ('tour_dismissed', 'product_tour', 2, 1),
            ('ad_clicked', 'linkedin_retargeting', 5, 1),
            ('lead_converted', 'linkedin_retargeting', 2, 1),
        ]
        for threshold in default_thresholds:
            cursor.execute('''
                INSERT INTO anomaly_thresholds 
                (event_type, campaign_name, min_expected, time_window_hours)
                VALUES (?, ?, ?, ?)
            ''', threshold)
    
    conn.commit()
    return conn

# ============================================
# FLASK WEBHOOK RECEIVER
# ============================================

def create_flask_app():
    """Create Flask app for webhook receiver"""
    flask_app = Flask(__name__)
    
    @flask_app.route('/webhook', methods=['POST'])
    def webhook_receiver():
        """Receive and validate webhook events"""
        try:
            # Validate JSON payload
            if not request.is_json:
                return jsonify({"error": "Content-Type must be application/json"}), 400
            
            payload = request.get_json()
            
            # Validate required fields
            required_fields = ['source', 'event_type']
            for field in required_fields:
                if field not in payload:
                    return jsonify({"error": f"Missing required field: {field}"}), 400
            
            # Validate source
            valid_sources = ['customer.io', 'appcues', 'linkedin']
            if payload['source'].lower() not in valid_sources:
                return jsonify({"error": f"Invalid source. Must be one of: {valid_sources}"}), 400
            
            # Validate event type based on source
            valid_events = {
                'customer.io': ['email_opened', 'email_clicked', 'email_bounced', 'email_unsubscribed'],
                'appcues': ['tour_started', 'tour_completed', 'tour_dismissed', 'flow_completed'],
                'linkedin': ['ad_clicked', 'ad_impression', 'lead_converted', 'form_submitted']
            }
            
            if payload['event_type'] not in valid_events.get(payload['source'].lower(), []):
                return jsonify({"error": f"Invalid event_type for source {payload['source']}"}), 400
            
            # Generate unique ID
            event_id = str(uuid.uuid4())
            
            # Store event
            conn = init_db()
            cursor = conn.cursor()
            
            timestamp = payload.get('timestamp', datetime.now().isoformat())
            
            cursor.execute('''
                INSERT INTO events (id, timestamp, source, event_type, campaign_name, user_email, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                event_id,
                timestamp,
                payload['source'].lower(),
                payload['event_type'],
                payload.get('campaign_name', ''),
                payload.get('user_email', ''),
                json.dumps(payload.get('metadata', {}))
            ))
            
            conn.commit()
            conn.close()
            
            return jsonify({
                "status": "success",
                "event_id": event_id,
                "message": "Event received and stored"
            }), 201
            
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    @flask_app.route('/health', methods=['GET'])
    def health_check():
        """Health check endpoint"""
        return jsonify({"status": "healthy"}), 200
    
    return flask_app

def run_flask_app():
    """Run Flask app in separate thread"""
    app = create_flask_app()
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

# ============================================
# STREAMLIT DASHBOARD
# ============================================

def load_events():
    """Load events from database"""
    conn = init_db()
    
    # Load events
    events_df = pd.read_sql_query('''
        SELECT * FROM events 
        ORDER BY timestamp DESC 
        LIMIT 1000
    ''', conn)
    
    # Load thresholds
    thresholds_df = pd.read_sql_query('SELECT * FROM anomaly_thresholds', conn)
    
    conn.close()
    
    # Convert timestamp to datetime
    if not events_df.empty:
        events_df['timestamp'] = pd.to_datetime(events_df['timestamp'])
    
    return events_df, thresholds_df

def check_anomalies(events_df, thresholds_df):
    """Check for anomalies based on thresholds"""
    anomalies = []
    
    if events_df.empty:
        return anomalies
    
    now = datetime.now()
    
    for _, threshold in thresholds_df.iterrows():
        # Filter events for this type and campaign
        mask = (events_df['event_type'] == threshold['event_type'])
        if threshold['campaign_name']:
            mask &= (events_df['campaign_name'] == threshold['campaign_name'])
        
        recent_events = events_df[mask].copy()
        
        # Check last hour
        one_hour_ago = now - timedelta(hours=1)
        recent_count = len(recent_events[recent_events['timestamp'] >= one_hour_ago])
        
        if recent_count < threshold['min_expected']:
            anomalies.append({
                'event_type': threshold['event_type'],
                'campaign_name': threshold['campaign_name'],
                'expected_min': threshold['min_expected'],
                'actual_count': recent_count,
                'status': 'Below Threshold'
            })
    
    return anomalies

def main():
    st.set_page_config(
        page_title="Campaign Health Dashboard",
        page_icon="📊",
        layout="wide"
    )
    
    st.title("Webhook Event Inspector & Campaign Health Dashboard")
    st.markdown("---")
    
    # Start Flask server in background if not already running
    if 'flask_started' not in st.session_state:
        flask_thread = threading.Thread(target=run_flask_app, daemon=True)
        flask_thread.start()
        st.session_state.flask_started = True
        time.sleep(1)  # Give Flask time to start
    
    # Load data
    events_df, thresholds_df = load_events()
    
    # Auto-refresh every 10 seconds
    if 'last_refresh' not in st.session_state:
        st.session_state.last_refresh = time.time()
    
    if time.time() - st.session_state.last_refresh > 10:
        st.session_state.last_refresh = time.time()
        st.rerun()
    
    # ============================================
    # TOP METRICS
    # ============================================
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_events = len(events_df)
        st.metric("Total Events", total_events, delta=None)
    
    with col2:
        if not events_df.empty:
            events_by_source = events_df['source'].value_counts()
            st.metric("Sources Active", len(events_by_source))
        else:
            st.metric("Sources Active", 0)
    
    with col3:
        if not events_df.empty:
            last_event_time = events_df['timestamp'].max().strftime("%H:%M:%S")
            st.metric("Last Event", last_event_time)
        else:
            st.metric("Last Event", "N/A")
    
    with col4:
        anomaly_count = len(check_anomalies(events_df, thresholds_df))
        st.metric("Anomalies Detected", anomaly_count, 
                 delta=None if anomaly_count == 0 else f"{anomaly_count} warnings")
    
    st.markdown("---")
    
    # ============================================
    # CHARTS ROW
    # ============================================
    
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.subheader("Events by Type & Source")
        
        if not events_df.empty:
            # Group by source and event_type
            grouped = events_df.groupby(['source', 'event_type']).size().reset_index(name='count')
            
            fig = px.bar(
                grouped,
                x='event_type',
                y='count',
                color='source',
                barmode='group',
                title="Event Distribution",
                labels={'count': 'Number of Events', 'event_type': 'Event Type'}
            )
            fig.update_layout(height=400)
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("No events received yet. Use the simulator to generate events.")
    
    with col_right:
        st.subheader("Event Volume (Last 24 Hours)")
        
        if not events_df.empty:
            # Create time series using floor with lowercase 'h'
            events_df_copy = events_df.copy()
            events_df_copy['hour'] = events_df_copy['timestamp'].dt.floor('h')
            time_series = events_df_copy.groupby(['hour', 'source']).size().reset_index(name='count')
            
            # Filter last 24 hours
            cutoff_time = datetime.now() - timedelta(hours=24)
            time_series = time_series[time_series['hour'] >= cutoff_time]
            
            fig = px.line(
                time_series,
                x='hour',
                y='count',
                color='source',
                title="Event Volume Over Time",
                labels={'count': 'Events', 'hour': 'Time'}
            )
            fig.update_layout(height=400)
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("No events to display in time series.")
    
    st.markdown("---")
    
    # ============================================
    # CAMPAIGN HEALTH PANEL
    # ============================================
    
    st.subheader("Campaign Health Monitor")
    
    anomalies = check_anomalies(events_df, thresholds_df)
    
    if anomalies:
        for anomaly in anomalies:
            with st.expander(
                f"Warning: {anomaly['event_type']} - {anomaly['campaign_name']} "
                f"({anomaly['actual_count']}/{anomaly['expected_min']} events)",
                expanded=True
            ):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric("Event Type", anomaly['event_type'])
                with col2:
                    st.metric("Expected (1hr)", anomaly['expected_min'])
                with col3:
                    st.metric("Actual (1hr)", anomaly['actual_count'], 
                             delta=anomaly['actual_count'] - anomaly['expected_min'])
                
                st.warning(
                    f"Campaign '{anomaly['campaign_name']}' is underperforming. "
                    f"Expected at least {anomaly['expected_min']} events in the last hour, "
                    f"but received only {anomaly['actual_count']}."
                )
    else:
        st.success("All campaigns are performing within expected thresholds.")
    
    st.markdown("---")
    
    # ============================================
    # RECENT EVENTS TABLE
    # ============================================
    
    st.subheader("Recent Events")
    
    if not events_df.empty:
        # Display recent events
        display_df = events_df.head(20)[['timestamp', 'source', 'event_type', 'campaign_name']].copy()
        display_df['timestamp'] = display_df['timestamp'].dt.strftime("%Y-%m-%d %H:%M:%S")
        st.dataframe(display_df, width='stretch', hide_index=True)
    else:
        st.info("No events received yet.")
    
    st.markdown("---")
    
    # ============================================
    # SIMULATOR SECTION
    # ============================================
    
    st.subheader("Event Simulator")
    st.markdown("Generate sample webhook events to test the dashboard.")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        num_events = st.slider("Number of events to generate", 5, 50, 10)
    
    with col2:
        include_anomalies = st.checkbox("Include anomaly scenarios", value=True)
    
    with col3:
        if st.button("Generate Events", type="primary"):
            generate_sample_events(num_events, include_anomalies)
            st.success(f"Generated {num_events} sample events!")
            st.rerun()
    
    # Display webhook endpoint info
    endpoint_info = """
    Webhook Endpoint: http://localhost:5000/webhook
    
    Expected Payload Format:
    {
        "source": "customer.io",
        "event_type": "email_opened",
        "campaign_name": "onboarding_sequence",
        "user_email": "user@example.com",
        "timestamp": "2024-01-01T12:00:00",
        "metadata": {}
    }
    """
    st.info(endpoint_info)

def generate_sample_events(num_events, include_anomalies):
    """Generate sample events and send to webhook"""
    import random
    import requests
    
    sources = ['customer.io', 'appcues', 'linkedin']
    events = {
        'customer.io': ['email_opened', 'email_clicked', 'email_bounced'],
        'appcues': ['tour_started', 'tour_completed', 'tour_dismissed'],
        'linkedin': ['ad_clicked', 'ad_impression', 'lead_converted']
    }
    
    campaigns = ['onboarding_sequence', 'product_tour', 'linkedin_retargeting', 'reengagement']
    
    successful = 0
    for i in range(num_events):
        source = random.choice(sources)
        event_type = random.choice(events[source])
        
        # If generating anomalies, reduce frequency of some events
        if include_anomalies and random.random() < 0.3:
            continue
        
        payload = {
            "source": source,
            "event_type": event_type,
            "campaign_name": random.choice(campaigns),
            "user_email": f"user{i}@example.com",
            "timestamp": datetime.now().isoformat(),
            "metadata": {
                "ip": f"192.168.1.{random.randint(1, 255)}",
                "user_agent": "Mozilla/5.0"
            }
        }
        
        try:
            response = requests.post(
                'http://localhost:5000/webhook',
                json=payload,
                timeout=2
            )
            if response.status_code == 201:
                successful += 1
        except requests.exceptions.ConnectionError:
            print("Flask server not running yet")
            break
    
    return successful

if __name__ == "__main__":
    main()
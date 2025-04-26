import requests
import json
import uuid
import logging
import base64
from datetime import datetime
from functools import wraps
from flask import request, session, g

# Configure logging
logging.basicConfig(filename='gtm_server.log', level=logging.INFO)
logger = logging.getLogger('gtm_server')

class GTMServerSide:
    def __init__(self, gtm_server_url, container_id, api_secret=None, container_config=None):
        """
        Initialize the GTM server-side tracking module.
        
        Args:
            gtm_server_url (str): URL of your GTM server container
            container_id (str): Your GTM container ID (GTM-XXXXXX)
            api_secret (str, optional): API secret for authenticated requests
            container_config (str, optional): Container configuration for manual provisioning
        """
        self.gtm_server_url = gtm_server_url
        self.container_id = container_id
        self.api_secret = api_secret
        self.container_config = container_config
        self.is_provisioned = False
        
        # Event history for debug interface - store last 50 events
        self.event_history = []
        self.max_history_size = 50
        
        # If container config is provided, we can attempt manual provisioning
        if self.container_config:
            self.manual_provision()
    
    def manual_provision(self):
        """
        Manually provision the GTM server using the container configuration.
        This sets up the connection to your GTM server.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Decode the container config if needed or use directly
            # Different GTM setups may require different provisioning approaches
            logger.info(f"Manually provisioning GTM server with container ID: {self.container_id}")
            
            # Here we would typically make an API call to the GTM server
            # to register this client using the container config
            # The exact API endpoint and payload depend on your GTM server setup
            
            # This is a placeholder for the actual provisioning logic
            # In a real implementation, you would make API calls to set up the server
            
            self.is_provisioned = True
            logger.info("Manual provisioning successful")
            return True
            
        except Exception as e:
            logger.error(f"Error during manual provisioning: {str(e)}")
            return False
    
    def _get_client_id(self):
        """Get or generate a persistent client ID."""
        if 'client_id' not in session:
            session['client_id'] = str(uuid.uuid4())
        return session['client_id']
    
    def _prepare_event(self, event_name, event_data=None):
        """Prepare event data with common parameters."""
        if event_data is None:
            event_data = {}
            
        # Add basic information
        event_data.update({
            'event': event_name,
            'client_id': self._get_client_id(),
            'page_location': request.url,
            'page_path': request.path,
            'page_referrer': request.referrer or '',
            'user_agent': request.user_agent.string,
            'timestamp': datetime.utcnow().isoformat(),
            'ip_override': request.remote_addr,
            'container_id': self.container_id
        })
        
        # Add user ID if available
        if hasattr(g, 'user') and g.user:
            event_data['user_id'] = g.user.id
            
        return event_data
    
    def send_event(self, event_name, event_data=None):
        """
        Send an event to the GTM server.
        
        Args:
            event_name (str): Name of the event
            event_data (dict, optional): Additional event data
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.is_provisioned and self.container_config:
            self.manual_provision()
            
        prepared_data = self._prepare_event(event_name, event_data)
        
        # Store in event history for debug interface
        event_record = {
            'timestamp': datetime.utcnow().isoformat(),
            'event_name': event_name,
            'data': prepared_data
        }
        self.event_history.insert(0, event_record)
        if len(self.event_history) > self.max_history_size:
            self.event_history.pop()
        
        # Construct the endpoint URL
        url = f"{self.gtm_server_url}/collect"
        if self.api_secret:
            url += f"?api_secret={self.api_secret}"
        
        # Add container config as a header if available
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'GTMServerSide-Flask/1.0'
        }
        
        if self.container_config:
            headers['X-GTM-Container-Config'] = self.container_config
        
        try:
            response = requests.post(
                url,
                json=prepared_data,
                headers=headers
            )
            
            if response.status_code == 200 or response.status_code == 204:
                logger.info(f"Event {event_name} sent successfully")
                return True
            else:
                logger.error(f"Failed to send event {event_name}. Status: {response.status_code}, Response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Exception while sending event {event_name}: {str(e)}")
            return False
    
    def get_recent_events(self, event_type=None, limit=10):
        """Return recent events for the debug interface.
        
        Args:
            event_type (str, optional): Filter by event type (page_view, view_item, etc)
            limit (int): Maximum number of events to return
            
        Returns:
            list: Recent events
        """
        if event_type:
            filtered_events = [event for event in self.event_history if event['event_name'] == event_type]
            return filtered_events[:limit]
        return self.event_history[:limit]
    
    def track_pageview(self):
        """Track a pageview event."""
        return self.send_event('page_view', {
            'page_title': request.endpoint
        })
    
    def track_purchase(self, transaction_id, value, currency='USD', items=None):
        """Track a purchase event."""
        purchase_data = {
            'transaction_id': transaction_id,
            'value': value,
            'currency': currency
        }
        
        if items:
            purchase_data['items'] = items
            
        return self.send_event('purchase', purchase_data)
    
    def track_add_to_cart(self, item_id, item_name, price, quantity=1, currency='USD'):
        """Track an add to cart event."""
        return self.send_event('add_to_cart', {
            'items': [{
                'item_id': item_id,
                'item_name': item_name,
                'price': price,
                'quantity': quantity,
                'currency': currency
            }]
        })

# Decorator for automatic page view tracking
def track_pageview(gtm_instance):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            result = f(*args, **kwargs)
            gtm_instance.track_pageview()
            return result
        return decorated_function
    return decorator
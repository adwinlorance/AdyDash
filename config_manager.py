from azure.appconfiguration import AzureAppConfigurationClient
from azure.identity import DefaultAzureCredential
import json
import os
import logging

logger = logging.getLogger(__name__)

# Default configuration if Azure App Configuration is not available
DEFAULT_CONFIG = {
    "stocks": {
        "Tech": ["AAPL", "MSFT", "GOOGL"],
        "Semiconductors": ["NVDA", "AMD"],
        "Electric Vehicles": ["TSLA"]
    }
}

class ConfigManager:
    def __init__(self):
        self.connection_string = os.getenv('AZURE_APP_CONFIG_CONNECTION_STRING')
        self.client = None
        self.init_client()

    def init_client(self):
        try:
            if self.connection_string:
                logger.info("Initializing Azure App Configuration with connection string")
                self.client = AzureAppConfigurationClient.from_connection_string(self.connection_string)
            else:
                # Fallback to managed identity
                logger.info("No connection string found, trying managed identity")
                credential = DefaultAzureCredential()
                endpoint = os.getenv('AZURE_APP_CONFIG_ENDPOINT')
                if endpoint:
                    self.client = AzureAppConfigurationClient(endpoint, credential)
                else:
                    logger.warning("No Azure App Configuration connection string or endpoint provided, will use default config")
        except Exception as e:
            logger.error(f"Failed to initialize Azure App Configuration client: {str(e)}")
            logger.warning("Will use default configuration")

    def get_stock_config(self):
        try:
            if not self.client:
                logger.warning("Using default configuration as no Azure App Configuration client is available")
                return DEFAULT_CONFIG
            
            # Get the stock configuration from Azure App Configuration
            logger.info("Fetching configuration from Azure App Configuration")
            setting = self.client.get_configuration_setting(key="stocks")
            if setting:
                logger.info("Successfully retrieved configuration from Azure App Configuration")
                return json.loads(setting.value)
            else:
                logger.warning("Stock configuration not found in Azure App Configuration, using default")
                return DEFAULT_CONFIG
        except Exception as e:
            logger.error(f"Error getting stock configuration: {str(e)}")
            logger.warning("Falling back to default configuration")
            return DEFAULT_CONFIG 
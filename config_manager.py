from azure.appconfiguration import AzureAppConfigurationClient
from azure.identity import DefaultAzureCredential
import json
import os
import logging

logger = logging.getLogger(__name__)

class ConfigManager:
    def __init__(self):
        self.connection_string = os.getenv('AZURE_APP_CONFIG_CONNECTION_STRING')
        self.client = None
        self.init_client()

    def init_client(self):
        try:
            if self.connection_string:
                self.client = AzureAppConfigurationClient.from_connection_string(self.connection_string)
            else:
                # Fallback to managed identity
                credential = DefaultAzureCredential()
                endpoint = os.getenv('AZURE_APP_CONFIG_ENDPOINT')
                if endpoint:
                    self.client = AzureAppConfigurationClient(endpoint, credential)
                else:
                    logger.error("No Azure App Configuration connection string or endpoint provided")
        except Exception as e:
            logger.error(f"Failed to initialize Azure App Configuration client: {str(e)}")

    def get_stock_config(self):
        try:
            if not self.client:
                raise Exception("Azure App Configuration client not initialized")
            
            # Get the stock configuration from Azure App Configuration
            setting = self.client.get_configuration_setting(key="stocks")
            if setting:
                return json.loads(setting.value)
            else:
                logger.error("Stock configuration not found in Azure App Configuration")
                return {"stocks": {}}
        except Exception as e:
            logger.error(f"Error getting stock configuration: {str(e)}")
            return {"stocks": {}} 
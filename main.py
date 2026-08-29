
from config import DEFAULT_CONFIG
from ui.app import UserInterface

if __name__ == "__main__":
    app = UserInterface(app_config=DEFAULT_CONFIG)
    app.run()
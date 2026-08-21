
from config import DEFAULT_CONFIG
from user_interface import UserInterface

if __name__ == "__main__":
    app = UserInterface(app_config=DEFAULT_CONFIG)
    app.run()
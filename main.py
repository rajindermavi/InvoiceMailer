# main.py
from config import (
    load_env_if_present,
    load_config,
    get_invoice_folder,
    get_soa_folder,
    get_client_directory,
)

def main():
    load_env_if_present()   # dev only, safe in prod
    cfg = load_config()

    invoice_folder = get_invoice_folder(cfg)
    soa_folder = get_soa_folder(cfg)
    client_directory = get_client_directory(cfg)

    # use these folders in the rest of your app
    # ...

if __name__ == "__main__":
    main()

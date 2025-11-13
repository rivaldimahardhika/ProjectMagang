import os
from cryptography.fernet import Fernet

def ensure_encryption_key(env_file=".env"):
    key = os.getenv("ENCRYPTION_KEY")
    if key:
        return key

    # buat key baru
    key = Fernet.generate_key().decode()

    # simpan ke .env
    with open(env_file, "a") as f:
        f.write(f"\nENCRYPTION_KEY={key}\n")
    print(f"[env_helper] ENCRYPTION_KEY baru dibuat dan disimpan ke {env_file}")
    
    return key

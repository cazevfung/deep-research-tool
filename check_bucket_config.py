import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from core.config import Config
import oss2

# Load config
config = Config()
access_key_id = config.get('scrapers.bilibili.oss_access_key_id')
access_key_secret = config.get('scrapers.bilibili.oss_access_key_secret')
bucket_name = config.get('oss.bucket')
endpoint = config.get('oss.endpoint')

# Create OSS client
auth = oss2.Auth(access_key_id, access_key_secret)
bucket = oss2.Bucket(auth, endpoint, bucket_name)

print(f"Checking bucket: {bucket_name}")
print("="*60)

# Check bucket info
try:
    info = bucket.get_bucket_info()
    print(f"\nBucket Info:")
    print(f"  Name: {info.name}")
    print(f"  Location: {info.location}")
    print(f"  Storage Class: {info.storage_class}")
    print(f"  ACL: {info.acl}")
    print(f"  Creation Date: {info.creation_date}")
except Exception as e:
    print(f"  Error: {e}")

# Check bucket ACL
try:
    acl = bucket.get_bucket_acl()
    print(f"\nBucket ACL: {acl.acl}")
except Exception as e:
    print(f"  Error: {e}")

# Check referer config (hotlink protection)
try:
    referer_config = bucket.get_bucket_referer()
    print(f"\nReferer Config (Hotlink Protection):")
    print(f"  Allow Empty Referer: {referer_config.allow_empty_referer}")
    print(f"  Referer List: {referer_config.referer_list}")
except Exception as e:
    print(f"  Error: {e}")

# Check bucket website config
try:
    website_config = bucket.get_bucket_website()
    print(f"\nWebsite Config:")
    print(f"  Index Document: {website_config.index_file}")
    print(f"  Error Document: {website_config.error_file}")
except Exception as e:
    print(f"  Website config not set or error: {e}")

print("\n" + "="*60)
print("\nRecommendation:")
print("If bucket forces download for HTML, you may need to:")
print("1. Check console: Bucket -> Basic Settings -> Hotlink Protection")
print("2. Or: Bucket -> Access Control -> Anti-Leech")
print("3. Look for 'Force Download' or similar option and disable it")



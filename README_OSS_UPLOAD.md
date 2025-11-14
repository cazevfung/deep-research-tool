# OSS Upload Service - Quick Start

## Overview

Upload HTML research reports to Alibaba Cloud OSS for public sharing.

## Features

✅ Upload HTML reports to OSS  
✅ Generate permanent public URLs  
✅ No authentication required to access  
✅ Share links with anyone  
✅ Reuse existing Bilibili scraper OSS credentials  

## Quick Start

### 1. One-Time Setup (2 minutes)

Your OSS bucket needs to allow public read access. See detailed guide:
- **[Manual Setup Guide](docs/OSS_MANUAL_SETUP_GUIDE.md)** ← Start here!

**Quick version:**
1. Go to https://oss.console.aliyun.com/
2. Select your bucket → **Access Control** → **Bucket Policy**
3. Add policy to allow public read on `research-reports/*`
4. Done! ✅

### 2. Upload Reports

```bash
# Generate HTML and upload in one command
python scripts/generate_export_html.py <session_id> --upload

# Example:
python scripts/generate_export_html.py 20251110_192142 --upload
```

### 3. Share the Link

Output will show:
```
📎 Public URL: https://transcription-services.oss-cn-beijing.aliyuncs.com/research-reports/report_20251110_192142.html
🔓 Access: Public (anyone with link can access)
```

Copy the URL and share! 🎉

## Usage Examples

### Generate and Upload
```bash
python scripts/generate_export_html.py 20251110_192142 --upload
```

### Upload Existing HTML
```bash
python scripts/generate_export_html.py --upload-only
```

### Custom Output Path
```bash
python scripts/generate_export_html.py 20251110_192142 --output my-report.html --upload
```

### Standalone Upload Service
```bash
# Upload any file
python services/oss_upload_service.py path/to/file.html --session-id 20251110_192142

# Upload as private
python services/oss_upload_service.py path/to/sensitive.html --private
```

## Configuration

The service uses OSS credentials from `config.yaml`:

```yaml
# Option 1: Use Bilibili scraper credentials (default)
scrapers:
  bilibili:
    oss_access_key_id: 'YOUR_KEY'
    oss_access_key_secret: 'YOUR_SECRET'
    oss_bucket: 'YOUR_BUCKET'
    oss_endpoint: 'https://oss-cn-beijing.aliyuncs.com'

# Option 2: Dedicated OSS config (optional)
oss:
  access_key_id: 'YOUR_KEY'          # Optional, falls back to bilibili config
  access_key_secret: 'YOUR_SECRET'   # Optional, falls back to bilibili config
  bucket: 'YOUR_BUCKET'              # Optional, falls back to bilibili config
  endpoint: 'https://oss-cn-beijing.aliyuncs.com'  # Optional
  reports_prefix: 'research-reports' # Folder in bucket (default: research-reports)
  set_public_acl: false              # Set to true if bucket allows object ACLs
```

## Troubleshooting

### URL Returns "AccessDenied" (403)

**Problem:** Bucket not configured for public access

**Solution:** Follow [Manual Setup Guide](docs/OSS_MANUAL_SETUP_GUIDE.md)

### "Put public object acl is not allowed"

**Problem:** Bucket blocks object-level ACLs (common security setting)

**Solution:** Use bucket-level policy instead:
1. Set `set_public_acl: false` in config.yaml (already default)
2. Configure bucket policy via OSS Console (see guide above)

### Missing OSS Credentials

**Problem:** No credentials in config.yaml

**Solution:** Add credentials:
```yaml
scrapers:
  bilibili:
    oss_access_key_id: 'YOUR_KEY_ID'
    oss_access_key_secret: 'YOUR_SECRET'
    oss_bucket: 'YOUR_BUCKET_NAME'
```

Get credentials from: https://ram.console.aliyun.com/manage/ak

## Security Considerations

### ✅ Safe for Sharing

Public HTML reports are great for:
- Non-sensitive research
- Reports meant for collaboration
- Public documentation

### ⚠️ Keep Private

Don't use public access for:
- Confidential information
- Personal/proprietary data  
- Sensitive research

For private sharing, keep bucket private and use signed URLs (see Manual Setup Guide).

## API Reference

### Python API

```python
from services.oss_upload_service import OSSUploadService

# Initialize service
service = OSSUploadService()

# Upload HTML report
result = service.upload_html_report(
    html_file_path='downloads/report.html',
    session_id='20251110_192142'
)

if result:
    print(f"Public URL: {result['url']}")
    print(f"Object Key: {result['object_key']}")
    print(f"Size: {result['size_bytes']} bytes")

# Upload any file
result = service.upload_file(
    file_path='path/to/file.pdf',
    object_key='custom/path/file.pdf',
    content_type='application/pdf',
    public=True
)

# List uploaded reports
reports = service.list_reports(prefix='research-reports')

# Delete a report
service.delete_file('research-reports/old_report.html')
```

## File Structure

```
services/
  oss_upload_service.py       # Main upload service
scripts/
  generate_export_html.py     # Generate and upload HTML
  setup_oss_public_bucket.py  # Helper for bucket config (may fail due to permissions)
docs/
  OSS_SETUP_FOR_PUBLIC_REPORTS.md  # Detailed configuration guide
  OSS_MANUAL_SETUP_GUIDE.md        # Manual setup instructions
```

## Cost Estimate

OSS is very affordable for HTML reports:

**100 Reports Example:**
- Storage: 100 × 2MB = 200MB → ¥0.024/month
- Traffic: 1,000 views × 2MB = 2GB → ¥1.00/month
- Requests: 1,000 GET requests → ¥0.001/month
- **Total: ~¥1.02/month** 💰

## Links

- **Setup Guide:** [docs/OSS_MANUAL_SETUP_GUIDE.md](docs/OSS_MANUAL_SETUP_GUIDE.md)
- **Detailed Docs:** [docs/OSS_SETUP_FOR_PUBLIC_REPORTS.md](docs/OSS_SETUP_FOR_PUBLIC_REPORTS.md)
- **Alibaba Cloud OSS Console:** https://oss.console.aliyun.com/
- **OSS Documentation:** https://www.alibabacloud.com/help/en/oss/

## Support

For issues or questions:
1. Check troubleshooting section above
2. Review setup guides in `docs/`
3. Check Alibaba Cloud OSS documentation

---

Made with ❤️ for easy research report sharing



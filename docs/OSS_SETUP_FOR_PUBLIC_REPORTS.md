# Setting Up Alibaba Cloud OSS for Public HTML Reports

This guide explains how to configure your Alibaba Cloud OSS bucket to serve HTML reports with public access.

## Overview

The Research Tool can upload generated HTML reports to Alibaba Cloud OSS (Object Storage Service) and make them publicly accessible via a permanent link. This allows you to easily share research reports with others.

## Configuration Options

There are two approaches to make files publicly accessible:

### Option 1: Bucket-Level Public Read Policy (Recommended)

Set the entire bucket (or a specific folder) to allow public read access. This is simpler and more flexible.

**Steps:**

1. **Go to OSS Console:**
   - Visit: https://oss.console.aliyun.com/
   - Select your bucket (e.g., `transcription-services`)

2. **Set Bucket ACL:**
   - Go to **Access Control** → **Bucket ACL**
   - Set to **Public Read** or **Public Read/Write**
   - Click **Save**

3. **Or use Bucket Policy (More Fine-Grained):**
   - Go to **Access Control** → **Bucket Policy**
   - Add a policy to allow public read on specific prefix:
   
   ```json
   {
     "Version": "1",
     "Statement": [
       {
         "Effect": "Allow",
         "Principal": ["*"],
         "Action": ["oss:GetObject"],
         "Resource": ["acs:oss:*:*:transcription-services/research-reports/*"]
       }
     ]
   }
   ```
   
   Replace `transcription-services` with your bucket name.

4. **Update config.yaml:**
   ```yaml
   oss:
     set_public_acl: false  # Don't set object-level ACL
     reports_prefix: 'research-reports'
   ```

### Option 2: Object-Level Public Read ACL

Set each uploaded file to have public-read ACL. Requires bucket to allow setting object ACLs.

**Steps:**

1. **Enable Object ACL in Bucket Settings:**
   - Go to OSS Console → Your Bucket → **Access Control** → **Bucket Policy**
   - Ensure the bucket allows setting object ACLs (this is usually the default)

2. **Update config.yaml:**
   ```yaml
   oss:
     set_public_acl: true  # Set ACL on each file
     reports_prefix: 'research-reports'
   ```

**Note:** If you see error `Put public object acl is not allowed`, your bucket has a policy blocking individual object ACLs. Use Option 1 instead.

## Using the Upload Service

### Generate and Upload in One Command

```bash
python scripts/generate_export_html.py <session_id> --upload
```

Example:
```bash
python scripts/generate_export_html.py 20251110_192142 --upload
```

### Upload Only (File Already Generated)

```bash
python scripts/generate_export_html.py --upload-only
```

### Standalone Upload Service

```bash
python services/oss_upload_service.py path/to/file.html --session-id 20251110_192142
```

## Testing Public Access

After uploading, test the public URL:

1. Copy the URL from the upload output:
   ```
   📎 Public URL: https://your-bucket.oss-cn-beijing.aliyuncs.com/research-reports/report_20251110_192142.html
   ```

2. Open the URL in:
   - An incognito/private browser window (no authentication)
   - A different device
   - Share with someone else

If the file loads without authentication, it's working correctly! 🎉

## Security Considerations

### ✅ Safe for Public Reports

Public HTML reports are fine for:
- Non-sensitive research findings
- Reports meant for sharing
- Public documentation

### ⚠️ Keep Private

Do NOT use public access for:
- Reports with confidential information
- Personal or proprietary data
- Sensitive research topics

**Alternative:** If you need restricted access, set `set_public_acl: false` and keep bucket private. Then share signed URLs with expiration:
```python
from services.oss_upload_service import OSSUploadService

service = OSSUploadService()
# Upload as private (set bucket to private)
result = service.upload_html_report('report.html', session_id='xxx')

# Generate signed URL (expires in 7 days)
from scrapers.bilibili_scraper import BilibiliScraper
scraper = BilibiliScraper()
signed_url = scraper._generate_signed_url(
    bucket_name='your-bucket',
    object_key=result['object_key'],
    access_key_id='your-key',
    access_key_secret='your-secret',
    expires=604800  # 7 days in seconds
)
```

## Cost Considerations

OSS charges for:
- **Storage:** ~¥0.12/GB/month (very cheap for HTML files)
- **Outbound Traffic:** ~¥0.50/GB (only when someone downloads)
- **Requests:** ~¥0.01 per 10,000 GET requests

**Example Cost for 100 Reports:**
- 100 reports × 2MB each = 200MB storage = ¥0.024/month
- 1,000 views × 2MB = 2GB traffic = ¥1.00/month
- Total: ~¥1.02/month

Very affordable! 💰

## Troubleshooting

### Error: "AccessDenied: Put public object acl is not allowed"

**Solution:** Your bucket blocks object-level ACLs. Use Option 1 (bucket-level policy) and set:
```yaml
oss:
  set_public_acl: false
```

### Error: "NoSuchBucket"

**Solution:** Check bucket name in `config.yaml` matches your OSS bucket exactly.

### Error: "InvalidAccessKeyId"

**Solution:** Verify OSS credentials in `config.yaml`:
```yaml
scrapers:
  bilibili:
    oss_access_key_id: 'YOUR_KEY'
    oss_access_key_secret: 'YOUR_SECRET'
    oss_bucket: 'YOUR_BUCKET'
```

### Public URL Returns 403 Forbidden

**Solution:** Bucket or object is not public. Check:
1. Bucket ACL is set to "Public Read"
2. Or bucket policy allows public GetObject
3. Object was uploaded with public access

### File Uploads but URL Shows XML Error

**Solution:** The file uploaded but isn't public. Set bucket to public read (Option 1).

## Advanced: Custom Domain (CDN)

For a nicer URL, you can bind a custom domain:

1. **Buy a domain** (e.g., `reports.yourcompany.com`)

2. **In OSS Console:**
   - Go to **Domain Management** → **Bind Custom Domain**
   - Enter your domain
   - Set CNAME record in your DNS provider

3. **Result:**
   ```
   Before: https://transcription-services.oss-cn-beijing.aliyuncs.com/research-reports/report.html
   After:  https://reports.yourcompany.com/research-reports/report.html
   ```

Much cleaner! ✨

## API Reference

See `services/oss_upload_service.py` for the full API:

```python
from services.oss_upload_service import OSSUploadService

service = OSSUploadService()

# Upload HTML report
result = service.upload_html_report(
    html_file_path='downloads/report.html',
    session_id='20251110_192142'
)

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

## Questions?

For issues or questions, check:
- Alibaba Cloud OSS Documentation: https://www.alibabacloud.com/help/en/oss/
- OSS Console: https://oss.console.aliyun.com/
- Project Documentation: `docs/`



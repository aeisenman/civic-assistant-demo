"""Object storage for uploads and generated certificates (SeaweedFS via boto3).

Called by app/workflows/intake.py and the certificate step in the engine.
Depends on: boto3 and the S3_* settings in app.config.
"""

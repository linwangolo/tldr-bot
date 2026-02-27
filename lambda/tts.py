"""
Amazon Polly text-to-speech: neural voice for short text, long-form (async) for longer summaries.
Returns audio bytes (sync) or the S3 key where the audio was written (async).
"""
import time
import boto3
from typing import Any

POLLY_VOICE = "Matthew"  # Neural English (US)
POLLY_ENGINE_NEURAL = "neural"
POLLY_ENGINE_LONG_FORM = "long-form"
SYNC_MAX_CHARS = 3000  # Use sync SynthesizeSpeech below this length


def _synthesize_sync(text: str, region: str | None = None) -> bytes:
    """Synchronous synthesis; returns MP3 bytes. Best for text <= 3000 chars."""
    client = boto3.client("polly", region_name=region or "us-east-1")
    if len(text) > SYNC_MAX_CHARS:
        text = text[:SYNC_MAX_CHARS] + "… [Summary truncated for audio.]"
    resp = client.synthesize_speech(
        VoiceId=POLLY_VOICE,
        OutputFormat="mp3",
        Text=text,
        Engine=POLLY_ENGINE_NEURAL,
    )
    return resp["AudioStream"].read()


def _synthesize_async(
    text: str,
    bucket: str,
    key_prefix: str,
    role_arn: str,
    region: str | None = None,
) -> str:
    """
    Long-form synthesis; Polly writes to S3. Poll until done, then return the S3 key of the output.
    Key will be {key_prefix}{TaskId}.mp3.
    """
    client = boto3.client("polly", region_name=region or "us-east-1")
    task = client.start_speech_synthesis_task(
        Engine=POLLY_ENGINE_LONG_FORM,
        LanguageCode="en-US",
        OutputFormat="mp3",
        OutputS3BucketName=bucket,
        OutputS3KeyPrefix=key_prefix,
        Text=text,
        VoiceId=POLLY_VOICE,
        ExecutionRoleArn=role_arn,
    )
    task_id = task["SynthesisTask"]["TaskId"]
    while True:
        out = client.get_speech_synthesis_task(TaskId=task_id)
        status = out["SynthesisTask"]["TaskStatus"]
        if status == "completed":
            return out["SynthesisTask"]["OutputUri"].replace(
                f"https://s3.{region or 'us-east-1'}.amazonaws.com/{bucket}/", ""
            ).lstrip("/")
        if status == "failed":
            raise RuntimeError(
                f"Polly task failed: {out['SynthesisTask'].get('FailureReason', 'unknown')}"
            )
        time.sleep(1)


def synthesize_to_s3(
    text: str,
    bucket: str,
    audio_key: str,
    polly_role_arn: str | None = None,
    region: str | None = None,
) -> str:
    """
    Synthesize text to MP3 and ensure it is stored at s3://bucket/audio_key.
    Uses sync Polly for short text (upload from Lambda); uses async Polly for long text
    then copies object to audio_key. Returns the final S3 key (same as audio_key).
    """
    s3 = boto3.client("s3", region_name=region or "us-east-1")
    if len(text) <= SYNC_MAX_CHARS:
        audio_bytes = _synthesize_sync(text, region)
        s3.put_object(Bucket=bucket, Key=audio_key, Body=audio_bytes, ContentType="audio/mpeg")
        return audio_key
    if not polly_role_arn:
        text = text[:SYNC_MAX_CHARS] + "… [Summary truncated for audio.]"
        audio_bytes = _synthesize_sync(text, region)
        s3.put_object(Bucket=bucket, Key=audio_key, Body=audio_bytes, ContentType="audio/mpeg")
        return audio_key
    # Long-form: prefix so we get a known pattern, then copy to final key
    prefix = audio_key.replace(".mp3", "-tmp-")
    raw_key = _synthesize_async(text, bucket, prefix, polly_role_arn, region)
    # Polly returns key like "audio/2026-02-26-tmp-<taskid>.mp3"
    s3.copy_object(
        CopySource={"Bucket": bucket, "Key": raw_key},
        Bucket=bucket,
        Key=audio_key,
        ContentType="audio/mpeg",
    )
    s3.delete_object(Bucket=bucket, Key=raw_key)
    return audio_key

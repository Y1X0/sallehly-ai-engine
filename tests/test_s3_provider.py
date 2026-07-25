"""Real, live-executed tests for S3Provider (Phase 8 WP4) - driven
against a genuine S3-compatible HTTP server, not a client-side mock.

A real MinIO server is not reachable in this sandbox: both
`docker pull minio/minio` (Docker Hub) and a direct `dl.min.io` binary
download are blocked by this environment's egress policy (the same
class of restriction ADR 0015/0016 hit for Temporal/Postgres, confirmed
via the agent-proxy's recentRelayFailures). `moto`'s `ThreadedMotoServer`
is used instead - not a mock library in the sense of stubbing responses,
but a genuine, separately-running HTTP server that implements the real
S3 API (the same server AWS SDK test suites use), listening on a real
local port that `S3Provider`'s `boto3` client talks to over real HTTP.
See docs/adr/0018-s3-storage-provider.md.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from storage_sdk import S3Provider

moto_server = pytest.importorskip("moto.server")


@pytest.fixture(scope="module")
def s3_server():
    server = moto_server.ThreadedMotoServer(port=0)
    server.start()
    host, port = server.get_host_and_port()
    yield f"http://{host}:{port}"
    server.stop()


@pytest.fixture
def provider(s3_server: str) -> S3Provider:
    p = S3Provider(
        "video-engine-assets",
        endpoint_url=s3_server,
        access_key="test",
        secret_key="test",
    )
    p._client.create_bucket(Bucket="video-engine-assets")
    return p


def _write_temp_file(content: bytes) -> Path:
    fd, path = tempfile.mkstemp()
    Path(path).write_bytes(content)
    return Path(path)


def test_put_returns_s3_uri(provider: S3Provider):
    source = _write_temp_file(b"hello world")
    uri = provider.put("videos/proj1/master.mp4", source)
    assert uri == "s3://video-engine-assets/videos/proj1/master.mp4"


def test_put_actually_uploads_bytes_readable_via_a_fresh_client(provider: S3Provider, s3_server: str):
    """Proves the upload is real - reads the object back through a brand
    new boto3 client/session, not the same provider instance."""
    import boto3

    source = _write_temp_file(b"real content, not a stub")
    provider.put("videos/proj1/master.mp4", source)

    fresh_client = boto3.client(
        "s3", endpoint_url=s3_server, aws_access_key_id="test", aws_secret_access_key="test", region_name="us-east-1"
    )
    body = fresh_client.get_object(Bucket="video-engine-assets", Key="videos/proj1/master.mp4")["Body"].read()
    assert body == b"real content, not a stub"


def test_exists_true_after_put(provider: S3Provider):
    source = _write_temp_file(b"data")
    provider.put("k1", source)
    assert provider.exists("k1") is True


def test_exists_false_for_missing_key(provider: S3Provider):
    assert provider.exists("does-not-exist") is False


def test_get_uri_does_not_require_the_key_to_exist(provider: S3Provider):
    assert provider.get_uri("not-uploaded-yet") == "s3://video-engine-assets/not-uploaded-yet"

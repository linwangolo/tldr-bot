#!/usr/bin/env python3
import aws_cdk as cdk
from tldr_ingest.tldr_ingest_stack import TldrIngestStack

app = cdk.App()
TldrIngestStack(app, "TldrIngestStack")
app.synth()

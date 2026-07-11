import logging
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from app.config import settings

logger = logging.getLogger(__name__)

def setup_tracing():
    """Configure OpenTelemetry tracing."""
    
    # Configure the basic resource info
    resource = Resource.create({
        "service.name": "hiring-pipeline",
        "service.version": "1.0.0"
    })

    # Set up the TracerProvider
    provider = TracerProvider(resource=resource)
    
    # If OTLP endpoint is set, export traces there (e.g., Jaeger, Honeycomb)
    if settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        try:
            otlp_exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT)
            provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            logger.info(f"Configured OTLP exporter to {settings.OTEL_EXPORTER_OTLP_ENDPOINT}")
        except Exception as e:
            logger.error(f"Failed to configure OTLP exporter: {e}")
            
    # For local dev, also print to console if no endpoint or just to be safe
    # But usually we don't want console spam. We'll only add console if no OTLP is set.
    if not settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        console_exporter = ConsoleSpanExporter()
        provider.add_span_processor(BatchSpanProcessor(console_exporter))
        logger.info("Configured console trace exporter")

    # Set the global default tracer provider
    trace.set_tracer_provider(provider)
    logger.info("OpenTelemetry tracing configured.")


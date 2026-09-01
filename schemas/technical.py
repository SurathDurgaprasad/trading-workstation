from pydantic import BaseModel, Field


class TechnicalAnalysis(BaseModel):
    trend: str = Field(description="Current trend direction and strength.")
    support_resistance: str = Field(
        description="Key support and resistance levels."
    )
    vwap: str = Field(description="VWAP analysis relative to price.")
    entry_quality: str = Field(description="Quality and timing of potential entry.")
    exit_quality: str = Field(description="Quality and timing of potential exit.")

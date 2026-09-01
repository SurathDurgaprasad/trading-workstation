from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

# Fixed, documented defaults — not tuned per dataset. The point of this split
# is infrastructure that prevents accidentally optimizing against the test
# period, not a claim that 60/20/20 is the "right" split (see spec §16).
DEFAULT_DEVELOPMENT_FRACTION = 0.6
DEFAULT_VALIDATION_FRACTION = 0.2
# out-of-sample gets whatever remains (defaults to 0.2)


class PeriodSplit(BaseModel):
    model_config = ConfigDict(frozen=True)

    development_start: datetime
    development_end: datetime
    validation_start: datetime
    validation_end: datetime
    out_of_sample_start: datetime
    out_of_sample_end: datetime

    @model_validator(mode="after")
    def _chronological_and_contiguous(self) -> "PeriodSplit":
        ordered = [
            self.development_start,
            self.development_end,
            self.validation_start,
            self.validation_end,
            self.out_of_sample_start,
            self.out_of_sample_end,
        ]
        if ordered != sorted(ordered):
            raise ValueError("PeriodSplit boundaries must be chronological and non-overlapping.")
        if self.development_end != self.validation_start:
            raise ValueError("development_end must equal validation_start (contiguous, no gap).")
        if self.validation_end != self.out_of_sample_start:
            raise ValueError("validation_end must equal out_of_sample_start (contiguous, no gap).")
        return self


def split_periods(
    start: datetime,
    end: datetime,
    *,
    development_fraction: float = DEFAULT_DEVELOPMENT_FRACTION,
    validation_fraction: float = DEFAULT_VALIDATION_FRACTION,
) -> PeriodSplit:
    if not (0 < development_fraction < 1) or not (0 < validation_fraction < 1):
        raise ValueError("development_fraction and validation_fraction must each be in (0, 1).")
    if development_fraction + validation_fraction >= 1:
        raise ValueError("development_fraction + validation_fraction must leave room for out-of-sample.")
    if end <= start:
        raise ValueError("end must be after start.")

    total = end - start
    development_end = start + total * development_fraction
    validation_end = development_end + total * validation_fraction

    return PeriodSplit(
        development_start=start,
        development_end=development_end,
        validation_start=development_end,
        validation_end=validation_end,
        out_of_sample_start=validation_end,
        out_of_sample_end=end,
    )

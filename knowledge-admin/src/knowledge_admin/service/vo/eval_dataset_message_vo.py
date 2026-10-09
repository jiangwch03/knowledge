"""测评集生成消息。"""

from pydantic import BaseModel, ConfigDict, Field


class EvalDatasetPending(BaseModel):
    """eval.dataset.pending 载荷。题数在测评集行上，消息只带主键。"""

    model_config = ConfigDict(populate_by_name=True)

    dataset_id: int = Field(description='测评集ID', alias='datasetId')

from typing import List, Optional, Dict, Literal, Any
from pydantic import BaseModel, Field

class GlobalConfig(BaseModel):
    agent: str
    notes: Optional[str] = None
    priority: Optional[str] = "normal"

class PairConfig(BaseModel):
    cameraAngle: Optional[str] = None
    style: Optional[str] = None
    mode: Optional[str] = None
    focus: Optional[str] = None
    notes: Optional[str] = None
    agent: Optional[str] = None  # To allow overriding the global agent per pair

class VideoContext(BaseModel):
    role: Literal["baseline", "current"]
    pairId: Optional[str] = None

class VideoMetadata(BaseModel):
    videoId: str
    downloadUrl: str
    localPath: Optional[str] = None
    context: VideoContext

class VideoSet(BaseModel):
    folderId: str
    videos: List[VideoMetadata]
    metadata: Dict[str, Any]

class ComparisonPair(BaseModel):
    baseline: VideoSet
    current: VideoSet
    config: PairConfig

class AthleteData(BaseModel):
    athleteId: Optional[str] = None
    name: Optional[str] = None
    # Add other athlete fields as needed
    class Config:
        extra = "allow"

class ComparisonPayload(BaseModel):
    analysisId: str
    comparisonId: str
    athleteId: str
    requestedBy: str
    timestamp: str
    uploadResultsUrl: str
    globalConfig: GlobalConfig
    analysisConfig: Optional[Dict[str, Any]] = None
    pairConfigs: Optional[List[PairConfig]] = []
    pairs: List[ComparisonPair]
    athleteData: Optional[AthleteData] = None
    outputFolderId: Optional[str] = None
    metadataPath: Optional[str] = None

    class Config:
        extra = "ignore"


from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from dice_detector.models import (
    AppConfig,
    DetectedDie,
    Modifier,
    ModifierPreset,
    RollResult,
    RollSession,
    RollType,
)

router = APIRouter()


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"


class StatusResponse(BaseModel):
    camera_active: bool = False
    session_active: bool = False
    session_id: str | None = None
    session_status: str | None = None
    connected_clients: int = 0


class StartSessionRequest(BaseModel):
    formula: str
    roll_name: str = ""
    roll_type: str = "custom"
    character_name: str = ""
    preset_name: str | None = None


class AcceptDiceRequest(BaseModel):
    dice: list[DetectedDie]


class ManualRollRequest(BaseModel):
    formula: str
    values: dict[str, list[int]]
    roll_name: str = ""
    roll_type: str = "custom"
    character_name: str = ""
    modifiers: list[Modifier] = []


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse()


@router.get("/status", response_model=StatusResponse)
async def get_status(request: Request) -> StatusResponse:
    state = request.app.state.app_state
    return StatusResponse(
        camera_active=False,
        session_active=state.current_session is not None,
        session_id=state.current_session.session_id if state.current_session else None,
        session_status=state.current_session.status.value if state.current_session else None,
        connected_clients=len(state.connected_clients),
    )


@router.get("/config", response_model=AppConfig)
async def get_config(request: Request) -> AppConfig:
    return request.app.state.config


@router.post("/config", response_model=AppConfig)
async def update_config(request: Request, config: AppConfig) -> AppConfig:
    request.app.state.config = config
    request.app.state.app_state.config = config
    return config


@router.get("/presets", response_model=list[ModifierPreset])
async def get_presets(request: Request) -> list[ModifierPreset]:
    return request.app.state.app_state.presets


@router.post("/presets", response_model=ModifierPreset)
async def add_preset(request: Request, preset: ModifierPreset) -> ModifierPreset:
    state = request.app.state.app_state
    state.add_preset(preset)
    return preset


@router.delete("/presets/{name}")
async def delete_preset(request: Request, name: str) -> dict:
    state = request.app.state.app_state
    if state.remove_preset(name):
        return {"status": "deleted", "name": name}
    raise HTTPException(status_code=404, detail=f"Preset '{name}' not found")


@router.post("/roll/start", response_model=RollSession)
async def start_roll_session(request: Request, req: StartSessionRequest) -> RollSession:
    state = request.app.state.app_state

    preset = None
    if req.preset_name:
        preset = state.get_preset(req.preset_name)

    try:
        roll_type = RollType(req.roll_type)
    except ValueError:
        roll_type = RollType.CUSTOM

    session = state.start_session(
        formula=req.formula,
        roll_name=req.roll_name,
        roll_type=roll_type,
        character_name=req.character_name,
        preset=preset,
    )

    return session


@router.get("/roll/current", response_model=RollSession | None)
async def get_current_session(request: Request) -> RollSession | None:
    return request.app.state.app_state.current_session


@router.post("/roll/accept", response_model=RollSession)
async def accept_dice(request: Request, req: AcceptDiceRequest) -> RollSession:
    state = request.app.state.app_state

    if state.current_session is None:
        raise HTTPException(status_code=400, detail="No active roll session")

    session = state.accept_dice(req.dice)
    if session is None:
        raise HTTPException(status_code=400, detail="Failed to accept dice")

    return session


@router.post("/roll/confirm", response_model=RollResult)
async def confirm_roll(request: Request) -> RollResult:
    state = request.app.state.app_state

    if state.current_session is None:
        raise HTTPException(status_code=400, detail="No active roll session")

    result = state.confirm_session()
    if result is None:
        raise HTTPException(status_code=400, detail="Failed to confirm session")

    return result


@router.post("/roll/cancel")
async def cancel_roll(request: Request) -> dict:
    state = request.app.state.app_state
    state.cancel_session()
    return {"status": "cancelled"}


@router.post("/roll/manual", response_model=RollResult)
async def manual_roll(request: Request, req: ManualRollRequest) -> RollResult:
    from dice_detector.models import BoundingBox, DiceType

    state = request.app.state.app_state

    try:
        roll_type = RollType(req.roll_type)
    except ValueError:
        roll_type = RollType.CUSTOM

    detected_dice: list[DetectedDie] = []
    for dice_type_str, values in req.values.items():

        try:
            dice_type = DiceType(dice_type_str)
        except ValueError:
            continue

        for value in values:
            detected_dice.append(
                DetectedDie(
                    dice_type=dice_type,
                    value=value,
                    confidence=1.0,
                    bbox=BoundingBox(x=0, y=0, width=1, height=1),
                    is_confirmed=True,
                )
            )

    session = state.start_session(
        formula=req.formula,
        roll_name=req.roll_name,
        roll_type=roll_type,
        character_name=req.character_name,
    )
    session.modifiers = req.modifiers
    state.accept_dice(detected_dice)
    result = state.confirm_session()

    if result is None:
        raise HTTPException(status_code=400, detail="Failed to create roll result")

    return result


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    state = websocket.app.state.app_state
    state.connected_clients.add(websocket)

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            elif msg_type == "start_session":
                try:
                    roll_type = RollType(data.get("roll_type", "custom"))
                except ValueError:
                    roll_type = RollType.CUSTOM

                session = state.start_session(
                    formula=data.get("formula", "1d20"),
                    roll_name=data.get("roll_name", ""),
                    roll_type=roll_type,
                    character_name=data.get("character_name", ""),
                )
                await websocket.send_json({
                    "type": "session_started",
                    "session": session.model_dump(mode="json"),
                })

            elif msg_type == "accept_dice":
                dice_data = data.get("dice", [])
                dice = [DetectedDie.model_validate(d) for d in dice_data]
                session = state.accept_dice(dice)
                if session:
                    await websocket.send_json({
                        "type": "session_updated",
                        "session": session.model_dump(mode="json"),
                    })

            elif msg_type == "confirm":
                result = state.confirm_session()
                if result:
                    await websocket.send_json({
                        "type": "roll_confirmed",
                        "result": result.model_dump(mode="json"),
                    })

            elif msg_type == "cancel":
                state.cancel_session()
                await websocket.send_json({"type": "session_cancelled"})

    except WebSocketDisconnect:
        state.connected_clients.discard(websocket)

from streamlit_webrtc import webrtc_streamer, WebRtcMode, ClientSettings
import av
import numpy as np
import io

AUDIO_SETTINGS = ClientSettings(
    rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
    media_stream_constraints={"audio": True, "video": False},
)

def grabar_audio_webrtc():
    st.subheader("🎙️ Grabación de Voz (WebRTC)")

    webrtc_ctx = webrtc_streamer(
        key="audio-recorder",
        mode=WebRtcMode.SENDONLY,
        client_settings=AUDIO_SETTINGS,
        audio_receiver_size=1024,
    )

    if not webrtc_ctx.audio_receiver:
        return None

    audio_frames = []

    try:
        while True:
            frame = webrtc_ctx.audio_receiver.get_frame(timeout=1)
            audio_frames.append(frame.to_ndarray())
    except:
        pass

    if len(audio_frames) == 0:
        return None

    # Convertir frames a bytes WAV
    audio_np = np.concatenate(audio_frames, axis=0)
    byte_io = io.BytesIO()

    import soundfile as sf
    sf.write(byte_io, audio_np, 48000, format="WAV")
    audio_bytes = byte_io.getvalue()

    st.audio(audio_bytes, format="audio/wav")

    return audio_bytes

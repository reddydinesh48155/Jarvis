"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ConnectionState, Room, RoomEvent, Track } from "livekit-client";

import { useAuth } from "@/hooks/use-auth";
import { getVoiceToken } from "@/lib/api";

type VoiceStatus = "connecting" | "connected" | "disconnected";

const ACK_TOPIC = "nova.voice.ack";

export function VoiceWorkspace() {
  const { user, accessToken, isLoading: isAuthLoading } = useAuth();
  const [status, setStatus] = useState<VoiceStatus>("disconnected");
  const [isMicEnabled, setIsMicEnabled] = useState(false);
  const [isUserSpeaking, setIsUserSpeaking] = useState(false);
  const [isAgentSpeaking, setIsAgentSpeaking] = useState(false);
  const [canPlayAudio, setCanPlayAudio] = useState(true);
  const [lastAcknowledgement, setLastAcknowledgement] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const roomRef = useRef<Room | null>(null);
  const connectRoomRef = useRef<() => Promise<void>>(async () => undefined);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const acknowledgementTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptRef = useRef(0);
  const isConnectingRef = useRef(false);
  const intentionalDisconnectRef = useRef(false);
  const audioContainerRef = useRef<HTMLDivElement>(null);

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current !== null) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const clearAudioElements = useCallback(() => {
    audioContainerRef.current?.querySelectorAll("audio").forEach((element) => element.remove());
  }, []);

  const scheduleReconnect = useCallback(() => {
    if (intentionalDisconnectRef.current || reconnectTimerRef.current !== null) {
      return;
    }
    const delay = Math.min(1000 * 2 ** reconnectAttemptRef.current, 8000);
    reconnectAttemptRef.current += 1;
    reconnectTimerRef.current = setTimeout(() => {
      reconnectTimerRef.current = null;
      void connectRoomRef.current();
    }, delay);
  }, []);

  const connectRoom = useCallback(async () => {
    if (!accessToken || isConnectingRef.current || roomRef.current?.state === ConnectionState.Connected) {
      return;
    }

    isConnectingRef.current = true;
    setStatus("connecting");
    setError(null);
    setIsUserSpeaking(false);
    setIsAgentSpeaking(false);

    const room = new Room({
      adaptiveStream: true,
      dynacast: true,
      disconnectOnPageLeave: true,
    });
    roomRef.current = room;

    room.on(RoomEvent.Reconnecting, () => {
      setStatus("connecting");
      setIsUserSpeaking(false);
      setIsAgentSpeaking(false);
    });
    room.on(RoomEvent.Reconnected, () => {
      reconnectAttemptRef.current = 0;
      setStatus("connected");
      setError(null);
    });
    room.on(RoomEvent.Disconnected, () => {
      if (roomRef.current === room) {
        roomRef.current = null;
      }
      setStatus("disconnected");
      setIsMicEnabled(false);
      setIsUserSpeaking(false);
      setIsAgentSpeaking(false);
      clearAudioElements();
      if (!intentionalDisconnectRef.current) {
        scheduleReconnect();
      }
    });
    room.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
      const localIdentity = room.localParticipant.identity;
      setIsUserSpeaking(speakers.some((participant) => participant.identity === localIdentity));
      setIsAgentSpeaking(speakers.some((participant) => participant.isAgent));
    });
    room.on(RoomEvent.ParticipantAttributesChanged, (attributes, participant) => {
      if (participant.isAgent && attributes["lk.agent.state"]) {
        setIsAgentSpeaking(attributes["lk.agent.state"] === "speaking");
      }
    });
    room.on(RoomEvent.TrackSubscribed, (track, _publication, participant) => {
      if (track.kind !== Track.Kind.Audio || !participant.isAgent) {
        return;
      }
      const audioElement = track.attach();
      audioElement.autoplay = true;
      audioElement.setAttribute("aria-label", "NOVA voice response");
      audioContainerRef.current?.appendChild(audioElement);
    });
    room.on(RoomEvent.TrackUnsubscribed, (track) => {
      track.detach().forEach((element) => element.remove());
    });
    room.on(RoomEvent.DataReceived, (payload, participant, _kind, topic) => {
      if (topic !== ACK_TOPIC || !participant?.isAgent) {
        return;
      }
      const message = new TextDecoder().decode(payload);
      setLastAcknowledgement(message);
      if (acknowledgementTimerRef.current !== null) {
        clearTimeout(acknowledgementTimerRef.current);
      }
      acknowledgementTimerRef.current = setTimeout(() => setLastAcknowledgement(null), 4000);
    });
    room.on(RoomEvent.AudioPlaybackStatusChanged, () => {
      setCanPlayAudio(room.canPlaybackAudio);
    });
    room.on(RoomEvent.TrackSubscriptionFailed, (_trackSid, participant) => {
      setError(`Could not subscribe to audio from ${participant.identity}.`);
    });

    try {
      const voiceSession = await getVoiceToken(accessToken);
      await room.connect(voiceSession.server_url, voiceSession.participant_token);
      await room.localParticipant.setMicrophoneEnabled(true);
      setIsMicEnabled(room.localParticipant.isMicrophoneEnabled);
      setCanPlayAudio(room.canPlaybackAudio);
      setStatus("connected");
      reconnectAttemptRef.current = 0;
    } catch (caughtError) {
      setStatus("disconnected");
      setError(caughtError instanceof Error ? caughtError.message : "Unable to connect to the voice room.");
      intentionalDisconnectRef.current = true;
      await room.disconnect().catch(() => undefined);
      intentionalDisconnectRef.current = false;
      if (roomRef.current === room) {
        roomRef.current = null;
      }
    } finally {
      isConnectingRef.current = false;
    }
  }, [accessToken, clearAudioElements, scheduleReconnect]);

  connectRoomRef.current = connectRoom;

  useEffect(() => {
    if (!accessToken) {
      return;
    }
    intentionalDisconnectRef.current = false;
    void connectRoom();

    return () => {
      intentionalDisconnectRef.current = true;
      clearReconnectTimer();
      if (acknowledgementTimerRef.current !== null) {
        clearTimeout(acknowledgementTimerRef.current);
      }
      const room = roomRef.current;
      roomRef.current = null;
      clearAudioElements();
      if (room) {
        void room.disconnect();
      }
    };
  }, [accessToken, clearAudioElements, clearReconnectTimer, connectRoom]);

  async function toggleMicrophone() {
    const room = roomRef.current;
    if (!room || status !== "connected") {
      return;
    }
    try {
      await room.localParticipant.setMicrophoneEnabled(!isMicEnabled);
      setIsMicEnabled(room.localParticipant.isMicrophoneEnabled);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Unable to change microphone state.");
    }
  }

  async function toggleConnection() {
    const room = roomRef.current;
    if (status === "connected" || status === "connecting") {
      intentionalDisconnectRef.current = true;
      clearReconnectTimer();
      if (room) {
        await room.disconnect();
      }
      roomRef.current = null;
      setStatus("disconnected");
      setIsMicEnabled(false);
      intentionalDisconnectRef.current = false;
      return;
    }
    intentionalDisconnectRef.current = false;
    await connectRoom();
  }

  async function enableAudio() {
    const room = roomRef.current;
    if (!room) {
      return;
    }
    try {
      await room.startAudio();
      setCanPlayAudio(room.canPlaybackAudio);
    } catch {
      setError("The browser blocked audio playback. Try clicking again.");
    }
  }

  if (isAuthLoading) {
    return <main className="flex min-h-screen items-center justify-center text-sm text-slate-500">Checking your session...</main>;
  }

  if (!user || !accessToken) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 px-6 py-12">
        <div className="rounded-3xl border border-slate-200 bg-white p-8 text-center shadow-panel">
          <p className="text-sm text-slate-500">Sign in to open the Voice Workspace.</p>
          <Link href="/login" className="mt-5 inline-flex rounded-xl bg-ink px-5 py-3 text-sm font-semibold text-white">Sign in</Link>
        </div>
      </main>
    );
  }

  const statusLabel = status === "connected" ? "Connected" : status === "connecting" ? "Connecting" : "Disconnected";
  const statusColor = status === "connected" ? "bg-emerald-500" : status === "connecting" ? "bg-amber-400" : "bg-slate-400";

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_right,_#ddd6fe,_transparent_35%),#f8fafc] px-6 py-10">
      <div className="mx-auto max-w-5xl">
        <header className="flex items-center justify-between">
          <Link href="/" className="flex items-center gap-3"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-ink font-bold text-white">N</span><span className="font-semibold tracking-tight text-ink">NOVA</span></Link>
          <Link href="/" className="text-sm font-semibold text-slate-500 hover:text-ink">Exit workspace</Link>
        </header>

        <section className="mt-20 grid gap-8 lg:grid-cols-[1.1fr_0.9fr] lg:items-end">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.24em] text-accent">Realtime transport</p>
            <h1 className="mt-5 text-5xl font-semibold tracking-tight text-ink sm:text-6xl">Voice Workspace</h1>
            <p className="mt-6 max-w-xl text-lg leading-8 text-slate-500">Connect your microphone to a private LiveKit room. Part 2 keeps the pipeline intentionally simple: the worker echoes captured audio and confirms each turn with a data message.</p>
          </div>
          <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-panel">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-slate-500">Room connection</span>
              <span className="flex items-center gap-2 text-sm font-semibold text-ink"><span className={`h-2.5 w-2.5 rounded-full ${statusColor}`} />{statusLabel}</span>
            </div>
            <div className="mt-6 grid grid-cols-2 gap-3">
              <ActivityIndicator active={isUserSpeaking} label="You" />
              <ActivityIndicator active={isAgentSpeaking} label="NOVA" />
            </div>
            <button onClick={() => void toggleConnection()} className="mt-6 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm font-semibold text-ink hover:border-slate-300">
              {status === "connected" || status === "connecting" ? "Disconnect" : "Reconnect"}
            </button>
          </div>
        </section>

        <section className="mt-8 rounded-3xl border border-slate-200 bg-white p-8 shadow-panel sm:p-10">
          <div className="flex flex-col items-center text-center">
            <div className={`flex h-36 w-36 items-center justify-center rounded-full transition ${isMicEnabled ? "bg-indigo-100" : "bg-slate-100"}`}>
              <span className={`text-5xl ${isMicEnabled ? "text-accent" : "text-slate-400"}`}>{isMicEnabled ? "◉" : "○"}</span>
            </div>
            <button onClick={() => void toggleMicrophone()} disabled={status !== "connected"} className="mt-7 rounded-xl bg-ink px-6 py-3 text-sm font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50">
              {isMicEnabled ? "Mute microphone" : "Unmute microphone"}
            </button>
            {!canPlayAudio && status === "connected" && <button onClick={() => void enableAudio()} className="mt-4 text-sm font-semibold text-accent hover:text-indigo-700">Click to enable NOVA audio</button>}
            {lastAcknowledgement && <p className="mt-5 rounded-full bg-indigo-50 px-4 py-2 text-sm font-semibold text-indigo-700">NOVA: {lastAcknowledgement}</p>}
            {error && <p className="mt-5 max-w-xl rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
          </div>
          <div ref={audioContainerRef} className="sr-only" aria-live="polite" />
        </section>
      </div>
    </main>
  );
}

function ActivityIndicator({ active, label }: { active: boolean; label: string }) {
  return (
    <div className={`rounded-2xl border px-4 py-4 text-center transition ${active ? "border-accent bg-indigo-50" : "border-slate-100 bg-slate-50"}`}>
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{label}</p>
      <p className={`mt-2 text-sm font-semibold ${active ? "text-accent" : "text-slate-500"}`}>{active ? "Speaking" : "Quiet"}</p>
    </div>
  );
}

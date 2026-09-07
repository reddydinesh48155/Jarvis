"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ConnectionState, Room, RoomEvent, Track } from "livekit-client";

import { useAuth } from "@/hooks/use-auth";
import { getVoiceToken } from "@/lib/api";

type VoiceStatus = "connecting" | "connected" | "disconnected";
type AgentLifecycleState = "listening" | "thinking" | "speaking";

const EVENT_TOPIC = "nova.voice.events";
const ACK_TOPIC = "nova.voice.ack";

interface ActiveAgentInfo {
  name: string;
  displayName: string;
  reason?: string;
}

const AGENT_BADGE_STYLES: Record<string, { bg: string; text: string; border: string; icon: string }> = {
  main_assistant: {
    bg: "bg-indigo-50",
    text: "text-indigo-700",
    border: "border-indigo-200",
    icon: "🤖",
  },
  research: {
    bg: "bg-emerald-50",
    text: "text-emerald-700",
    border: "border-emerald-200",
    icon: "🔬",
  },
  coding: {
    bg: "bg-violet-50",
    text: "text-violet-700",
    border: "border-violet-200",
    icon: "💻",
  },
  productivity: {
    bg: "bg-amber-50",
    text: "text-amber-700",
    border: "border-amber-200",
    icon: "⚡",
  },
};

export function VoiceWorkspace() {
  const { user, accessToken, isLoading: isAuthLoading } = useAuth();
  const [status, setStatus] = useState<VoiceStatus>("disconnected");
  const [agentState, setAgentState] = useState<AgentLifecycleState>("listening");
  const [activeAgent, setActiveAgent] = useState<ActiveAgentInfo>({
    name: "main_assistant",
    displayName: "Main Assistant",
  });
  const [userTranscript, setUserTranscript] = useState<string | null>(null);
  const [agentTranscript, setAgentTranscript] = useState<string | null>(null);

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
      setAgentState("listening");
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
      if (participant.isAgent) {
        const stateAttr = attributes["lk.agent.state"] as AgentLifecycleState | undefined;
        if (stateAttr) {
          setAgentState(stateAttr);
          setIsAgentSpeaking(stateAttr === "speaking");
        }
        const agentName = attributes["nova.agent.name"];
        const agentDisplay = attributes["nova.agent.display_name"];
        if (agentName && agentDisplay) {
          setActiveAgent({ name: agentName, displayName: agentDisplay });
        }
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
      if (!participant?.isAgent) {
        return;
      }

      if (topic === EVENT_TOPIC) {
        try {
          const raw = new TextDecoder().decode(payload);
          const data = JSON.parse(raw);

          if (data.type === "agent_state") {
            setAgentState(data.state);
            setIsAgentSpeaking(data.state === "speaking");
            if (data.agent_display_name) {
              setActiveAgent({
                name: data.agent_name || "main_assistant",
                displayName: data.agent_display_name,
              });
            }
          } else if (data.type === "active_agent") {
            setActiveAgent({
              name: data.name,
              displayName: data.display_name,
              reason: data.reason,
            });
          } else if (data.type === "user_transcript") {
            setUserTranscript(data.text);
          } else if (data.type === "agent_transcript") {
            setAgentTranscript(data.text);
            if (data.agent_display_name) {
              setActiveAgent({
                name: data.agent_name || "main_assistant",
                displayName: data.agent_display_name,
              });
            }
          } else if (data.type === "error") {
            setError(data.message || "An error occurred during voice processing.");
          }
        } catch {
          // Ignore invalid JSON payloads
        }
      } else if (topic === ACK_TOPIC) {
        const message = new TextDecoder().decode(payload);
        setLastAcknowledgement(message);
        if (acknowledgementTimerRef.current !== null) {
          clearTimeout(acknowledgementTimerRef.current);
        }
        acknowledgementTimerRef.current = setTimeout(() => setLastAcknowledgement(null), 5000);
      }
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

  const lifecycleLabel =
    agentState === "thinking"
      ? "Thinking & Routing..."
      : agentState === "speaking"
      ? "Speaking"
      : "Listening";

  const lifecycleColor =
    agentState === "thinking"
      ? "bg-amber-400 animate-pulse"
      : agentState === "speaking"
      ? "bg-indigo-500 animate-pulse"
      : "bg-emerald-500";

  const badgeStyle = AGENT_BADGE_STYLES[activeAgent.name] || AGENT_BADGE_STYLES.main_assistant;

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_right,_#ddd6fe,_transparent_35%),#f8fafc] px-6 py-10">
      <div className="mx-auto max-w-5xl">
        <header className="flex items-center justify-between">
          <Link href="/" className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-ink font-bold text-white">N</span>
            <span className="font-semibold tracking-tight text-ink">NOVA</span>
          </Link>
          <div className="flex items-center gap-4">
            {/* Active Agent Badge */}
            <div className={`flex items-center gap-2 rounded-full border px-3.5 py-1.5 text-xs font-semibold ${badgeStyle.border} ${badgeStyle.bg} ${badgeStyle.text}`}>
              <span>{badgeStyle.icon}</span>
              <span>{activeAgent.displayName}</span>
            </div>
            <Link href="/" className="text-sm font-semibold text-slate-500 hover:text-ink">Exit workspace</Link>
          </div>
        </header>

        <section className="mt-14 grid gap-8 lg:grid-cols-[1.1fr_0.9fr] lg:items-end">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.24em] text-accent">Multi-Agent Voice Pipeline</p>
            <h1 className="mt-4 text-4xl font-semibold tracking-tight text-ink sm:text-5xl">Voice Workspace</h1>
            <p className="mt-4 max-w-xl text-base leading-7 text-slate-600">
              Speak naturally into your microphone. NOVA routes your requests to specialized agents (Main Assistant, Research, Coding, and Productivity) with live speech recognition, real-time reasoning, and synthesized voice responses.
            </p>
          </div>

          <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-panel">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-slate-500">Room connection</span>
              <span className="flex items-center gap-2 text-sm font-semibold text-ink">
                <span className={`h-2.5 w-2.5 rounded-full ${statusColor}`} />
                {statusLabel}
              </span>
            </div>

            {/* Lifecycle Status & Active Agent */}
            <div className="mt-4 flex items-center justify-between rounded-2xl bg-slate-50 p-3 border border-slate-100">
              <span className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">Agent Status</span>
              <span className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                <span className={`h-2.5 w-2.5 rounded-full ${lifecycleColor}`} />
                {lifecycleLabel}
              </span>
            </div>

            <div className="mt-4 grid grid-cols-2 gap-3">
              <ActivityIndicator active={isUserSpeaking} label="You" stateText={isUserSpeaking ? "Speaking" : "Quiet"} />
              <ActivityIndicator
                active={isAgentSpeaking || agentState === "speaking"}
                label={activeAgent.displayName}
                stateText={agentState === "thinking" ? "Thinking" : agentState === "speaking" ? "Speaking" : "Ready"}
              />
            </div>

            <button
              onClick={() => void toggleConnection()}
              className="mt-5 w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-ink hover:border-slate-300"
            >
              {status === "connected" || status === "connecting" ? "Disconnect" : "Reconnect"}
            </button>
          </div>
        </section>

        {/* Live Interaction & Transcript Section */}
        <section className="mt-8 rounded-3xl border border-slate-200 bg-white p-6 shadow-panel sm:p-8">
          <div className="flex flex-col items-center text-center">
            <div
              className={`flex h-32 w-32 items-center justify-center rounded-full transition-all duration-300 ${
                agentState === "speaking"
                  ? "bg-indigo-100 ring-8 ring-indigo-50"
                  : agentState === "thinking"
                  ? "bg-amber-100 ring-8 ring-amber-50"
                  : isMicEnabled
                  ? "bg-indigo-50 ring-4 ring-indigo-50"
                  : "bg-slate-100"
              }`}
            >
              <span className={`text-4xl ${isMicEnabled ? "text-accent" : "text-slate-400"}`}>
                {agentState === "thinking" ? "⏳" : agentState === "speaking" ? "🔊" : isMicEnabled ? "🎙️" : "🔇"}
              </span>
            </div>

            <div className="mt-5 flex items-center gap-3">
              <button
                onClick={() => void toggleMicrophone()}
                disabled={status !== "connected"}
                className="rounded-xl bg-ink px-5 py-2.5 text-sm font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isMicEnabled ? "Mute microphone" : "Unmute microphone"}
              </button>
              {!canPlayAudio && status === "connected" && (
                <button onClick={() => void enableAudio()} className="text-sm font-semibold text-accent hover:text-indigo-700">
                  Click to enable audio
                </button>
              )}
            </div>

            {error && (
              <p className="mt-4 max-w-xl rounded-xl bg-red-50 px-4 py-2.5 text-sm text-red-700 border border-red-200">
                {error}
              </p>
            )}
          </div>

          {/* Live Transcripts */}
          <div className="mt-8 grid gap-4 border-t border-slate-100 pt-6 sm:grid-cols-2">
            {/* User Transcript Card */}
            <div className="rounded-2xl border border-slate-200 bg-slate-50/60 p-5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">Your Speech</span>
                <span className="text-xs text-slate-400">Microphone</span>
              </div>
              <p className="mt-3 text-sm leading-relaxed text-slate-700">
                {userTranscript || <span className="italic text-slate-400">Say something to NOVA...</span>}
              </p>
            </div>

            {/* Agent Transcript Card */}
            <div className="rounded-2xl border border-indigo-100 bg-indigo-50/40 p-5">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.16em] text-indigo-600">
                  <span>{badgeStyle.icon}</span>
                  <span>{activeAgent.displayName}</span>
                </span>
                <span className="text-xs font-medium text-indigo-400">
                  {agentState === "thinking" ? "Thinking..." : agentState === "speaking" ? "Speaking" : "Response"}
                </span>
              </div>
              <p className="mt-3 text-sm leading-relaxed text-slate-800">
                {agentTranscript || lastAcknowledgement || (
                  <span className="italic text-slate-400">Waiting for response...</span>
                )}
              </p>
            </div>
          </div>
          <div ref={audioContainerRef} className="sr-only" aria-live="polite" />
        </section>
      </div>
    </main>
  );
}

function ActivityIndicator({ active, label, stateText }: { active: boolean; label: string; stateText: string }) {
  return (
    <div
      className={`rounded-2xl border px-3 py-3 text-center transition ${
        active ? "border-accent bg-indigo-50" : "border-slate-100 bg-slate-50"
      }`}
    >
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400 truncate">{label}</p>
      <p className={`mt-1 text-sm font-semibold ${active ? "text-accent" : "text-slate-500"}`}>{stateText}</p>
    </div>
  );
}

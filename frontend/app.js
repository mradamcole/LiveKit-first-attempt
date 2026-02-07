/**
 * LiveKit Voice Assistant — Frontend Logic
 *
 * Handles:
 *  - Fetching config and tokens from the FastAPI backend
 *  - Connecting to a LiveKit room
 *  - Web Speech API for browser-side STT
 *  - Sending user text to the agent via lk.chat
 *  - Receiving agent text via lk.transcription
 *  - Playing agent TTS audio via track subscription
 *  - Updating the system prompt via RPC
 *  - Displaying agent state (listening/thinking/speaking)
 */

import {
  Room,
  RoomEvent,
  Track,
  ConnectionState,
  ParticipantKind,
} from 'https://esm.sh/livekit-client@2';

// ===== DOM Elements =====
const connectBtn = document.getElementById('connect-btn');
const micBtn = document.getElementById('mic-btn');
const micLabel = document.getElementById('mic-label');
const systemPromptEl = document.getElementById('system-prompt');
const promptStatus = document.getElementById('prompt-status');
const transcriptMessages = document.getElementById('transcript-messages');
const connectionStatusEl = document.getElementById('connection-status');
const agentStateEl = document.getElementById('agent-state');
const agentAudioEl = document.getElementById('agent-audio');
const browserWarning = document.getElementById('browser-warning');
const appEl = document.getElementById('app');

// ===== State =====
let room = null;
let agentIdentity = null;
let isListening = false;
let recognition = null;
let currentInterimEl = null;
let promptDebounceTimer = null;

// ===== Browser Check =====
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
if (!SpeechRecognition) {
  browserWarning.hidden = false;
  appEl.style.display = 'none';
}

// ===== Init: Load Config =====
async function loadConfig() {
  try {
    const res = await fetch('/api/config');
    const data = await res.json();
    systemPromptEl.value = data.default_system_prompt || '';
  } catch (err) {
    console.error('Failed to load config:', err);
    systemPromptEl.placeholder = 'Failed to load default prompt';
  }
}

loadConfig();

// ===== LiveKit Connection =====
async function connect() {
  const identity = `user-${Math.random().toString(36).slice(2, 8)}`;

  // Fetch token
  const res = await fetch(`/api/token?identity=${encodeURIComponent(identity)}`);
  const { token, url } = await res.json();

  // Create room
  room = new Room();

  // --- Register ALL handlers BEFORE connecting ---

  // Track subscription (agent TTS audio)
  room.on(RoomEvent.TrackSubscribed, (track, publication, participant) => {
    if (track.kind === Track.Kind.Audio) {
      track.attach(agentAudioEl);
    }
  });

  room.on(RoomEvent.TrackUnsubscribed, (track) => {
    track.detach();
  });

  // Discover agent identity
  room.on(RoomEvent.ParticipantConnected, (participant) => {
    if (participant.kind === ParticipantKind.AGENT) {
      agentIdentity = participant.identity;
      agentStateEl.hidden = false;
      agentStateEl.textContent = 'Agent: connected';
      // Send current system prompt to the newly connected agent
      sendSystemPrompt();
    }
  });

  room.on(RoomEvent.ParticipantDisconnected, (participant) => {
    if (participant.identity === agentIdentity) {
      agentIdentity = null;
      agentStateEl.textContent = 'Agent: disconnected';
      agentStateEl.className = 'status-indicator disconnected';
    }
  });

  // Agent state changes
  room.on(RoomEvent.ParticipantAttributesChanged, (changedAttributes, participant) => {
    if (participant.identity === agentIdentity) {
      const state = participant.attributes['lk.agent.state'];
      if (state) {
        agentStateEl.textContent = `Agent: ${state}`;
        agentStateEl.className = `status-indicator agent-${state}`;
      }
    }
  });

  // Connection state
  room.on(RoomEvent.ConnectionStateChanged, (state) => {
    updateConnectionStatus(state);
  });

  // Receive agent text via lk.transcription
  room.registerTextStreamHandler('lk.transcription', async (reader, participantIdentity) => {
    // Only show agent messages (not user transcriptions echoed back)
    if (participantIdentity === agentIdentity || participantIdentity !== room.localParticipant.identity) {
      const text = await reader.readAll();
      if (text.trim()) {
        addMessage('agent', text);
      }
    }
  });

  // --- Now connect ---
  await room.connect(url, token);

  // Check if agent is already in the room
  for (const [, participant] of room.remoteParticipants) {
    if (participant.kind === ParticipantKind.AGENT) {
      agentIdentity = participant.identity;
      agentStateEl.hidden = false;
      agentStateEl.textContent = 'Agent: connected';
      sendSystemPrompt();
      break;
    }
  }

  // Update UI
  connectBtn.textContent = 'Disconnect';
  connectBtn.classList.add('connected');
  micBtn.disabled = false;
}

function disconnect() {
  if (room) {
    room.disconnect();
    room = null;
  }
  agentIdentity = null;
  stopListening();
  connectBtn.textContent = 'Connect';
  connectBtn.classList.remove('connected');
  micBtn.disabled = true;
  agentStateEl.hidden = true;
  updateConnectionStatus(ConnectionState.Disconnected);
}

function updateConnectionStatus(state) {
  const labels = {
    [ConnectionState.Disconnected]: ['Disconnected', 'disconnected'],
    [ConnectionState.Connecting]: ['Connecting...', 'connecting'],
    [ConnectionState.Connected]: ['Connected', 'connected'],
    [ConnectionState.Reconnecting]: ['Reconnecting...', 'connecting'],
  };
  const [text, cls] = labels[state] || ['Unknown', 'disconnected'];
  connectionStatusEl.textContent = text;
  connectionStatusEl.className = `status-indicator ${cls}`;
}

connectBtn.addEventListener('click', () => {
  if (room) {
    disconnect();
  } else {
    connectBtn.disabled = true;
    connectBtn.textContent = 'Connecting...';
    connect()
      .catch((err) => {
        console.error('Connection failed:', err);
        disconnect();
        alert('Failed to connect: ' + err.message);
      })
      .finally(() => {
        connectBtn.disabled = false;
      });
  }
});

// ===== Web Speech API (STT) =====
function startListening() {
  if (!SpeechRecognition || !room) return;

  recognition = new SpeechRecognition();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = 'en-US';

  recognition.onresult = (event) => {
    let interim = '';
    let final = '';

    for (let i = event.resultIndex; i < event.results.length; i++) {
      const transcript = event.results[i][0].transcript;
      if (event.results[i].isFinal) {
        final += transcript;
      } else {
        interim += transcript;
      }
    }

    // Show interim text
    if (interim) {
      updateInterim(interim);
    }

    // Process final text
    if (final) {
      clearInterim();
      addMessage('user', final.trim());
      sendTextToAgent(final.trim());
    }
  };

  recognition.onerror = (event) => {
    console.error('Speech recognition error:', event.error);
    // Recoverable errors -- restart
    if (event.error === 'no-speech' || event.error === 'aborted') {
      // Will restart via onend
    }
  };

  recognition.onend = () => {
    // Re-start if we're still supposed to be listening
    if (isListening) {
      try {
        recognition.start();
      } catch (e) {
        // May throw if already started
      }
    }
  };

  recognition.start();
  isListening = true;
  micBtn.classList.add('active');
  micLabel.textContent = 'Stop Mic';
}

function stopListening() {
  isListening = false;
  if (recognition) {
    recognition.abort();
    recognition = null;
  }
  clearInterim();
  micBtn.classList.remove('active');
  micLabel.textContent = 'Start Mic';
}

micBtn.addEventListener('click', () => {
  if (isListening) {
    stopListening();
  } else {
    startListening();
  }
});

// ===== Send Text to Agent =====
async function sendTextToAgent(text) {
  if (!room || !room.localParticipant) return;
  try {
    await room.localParticipant.sendText(text, { topic: 'lk.chat' });
  } catch (err) {
    console.error('Failed to send text:', err);
  }
}

// ===== System Prompt RPC =====
async function sendSystemPrompt() {
  if (!room || !agentIdentity) return;
  const prompt = systemPromptEl.value.trim();
  if (!prompt) return;

  try {
    await room.localParticipant.performRpc({
      destinationIdentity: agentIdentity,
      method: 'update_system_prompt',
      payload: prompt,
    });
    promptStatus.textContent = 'Saved';
    setTimeout(() => { promptStatus.textContent = ''; }, 2000);
  } catch (err) {
    console.error('Failed to update system prompt:', err);
    promptStatus.textContent = 'Failed to save';
    promptStatus.style.color = 'var(--danger)';
    setTimeout(() => {
      promptStatus.textContent = '';
      promptStatus.style.color = '';
    }, 3000);
  }
}

// Debounced system prompt update
systemPromptEl.addEventListener('input', () => {
  clearTimeout(promptDebounceTimer);
  promptDebounceTimer = setTimeout(() => {
    sendSystemPrompt();
  }, 500);
});

// ===== Transcript UI =====
function addMessage(role, text) {
  const el = document.createElement('div');
  el.className = `message ${role}`;

  const label = document.createElement('span');
  label.className = 'label';
  label.textContent = role === 'user' ? 'You' : 'Agent';

  const content = document.createTextNode(text);

  el.appendChild(label);
  el.appendChild(content);
  transcriptMessages.appendChild(el);
  scrollToBottom();
}

function updateInterim(text) {
  if (!currentInterimEl) {
    currentInterimEl = document.createElement('div');
    currentInterimEl.className = 'message user interim';

    const label = document.createElement('span');
    label.className = 'label';
    label.textContent = 'You (listening...)';

    currentInterimEl.appendChild(label);
    currentInterimEl.appendChild(document.createTextNode(''));
    transcriptMessages.appendChild(currentInterimEl);
  }

  // Update text content (keep the label, replace the text node)
  currentInterimEl.lastChild.textContent = text;
  scrollToBottom();
}

function clearInterim() {
  if (currentInterimEl) {
    currentInterimEl.remove();
    currentInterimEl = null;
  }
}

function scrollToBottom() {
  const panel = document.getElementById('transcript-panel');
  panel.scrollTop = panel.scrollHeight;
}

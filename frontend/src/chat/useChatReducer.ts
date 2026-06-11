import { useReducer, useCallback } from "react";
import type {
  ChatMessageOut,
  PatchOp,
  Workflow,
} from "../types-platform";

export interface ChatMessage extends ChatMessageOut {
  patch?: PatchOp[] | null;
  referenceWorkflow?: Workflow | null;
  hasError?: boolean;
  retryUserContent?: string;
}

export interface ChatState {
  messages: ChatMessage[];
  isStreaming: boolean;
  error: string | null;
}

type Action =
  | { type: "setMessages"; messages: ChatMessage[] }
  | { type: "appendUser"; message: ChatMessage }
  | { type: "appendAssistant"; message: ChatMessage }
  | { type: "setStreaming"; value: boolean }
  | { type: "setError"; error: string | null };

const INITIAL_STATE: ChatState = {
  messages: [],
  isStreaming: false,
  error: null,
};

function reducer(state: ChatState, action: Action): ChatState {
  switch (action.type) {
    case "setMessages":
      return { ...state, messages: action.messages, error: null };
    case "appendUser":
      return { ...state, messages: [...state.messages, action.message] };
    case "appendAssistant":
      return { ...state, messages: [...state.messages, action.message] };
    case "setStreaming":
      return { ...state, isStreaming: action.value };
    case "setError":
      return { ...state, error: action.error };
    default:
      return state;
  }
}

export interface ChatReducerApi {
  state: ChatState;
  appendUser: (message: ChatMessage) => void;
  appendAssistant: (message: ChatMessage) => void;
  setStreaming: (value: boolean) => void;
  setError: (error: string | null) => void;
  setMessages: (messages: ChatMessage[]) => void;
}

export function useChatReducer(): ChatReducerApi {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);

  const appendUser = useCallback(
    (message: ChatMessage) => dispatch({ type: "appendUser", message }),
    [],
  );
  const appendAssistant = useCallback(
    (message: ChatMessage) => dispatch({ type: "appendAssistant", message }),
    [],
  );
  const setStreaming = useCallback(
    (value: boolean) => dispatch({ type: "setStreaming", value }),
    [],
  );
  const setError = useCallback(
    (error: string | null) => dispatch({ type: "setError", error }),
    [],
  );
  const setMessages = useCallback(
    (messages: ChatMessage[]) => dispatch({ type: "setMessages", messages }),
    [],
  );

  return { state, appendUser, appendAssistant, setStreaming, setError, setMessages };
}

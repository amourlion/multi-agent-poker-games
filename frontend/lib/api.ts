export type SeatType = 'random' | 'llm' | 'human';
export interface SeatConfig {
  name: string;
  type: SeatType;
  stack: number;
  bet_mode?: 'heuristic' | 'llm';
}

export interface GameStateResponse {
  game_id: string;
  state: GameState;
  result: GameResult | null;
}

export interface GameState {
  game_id: number;
  phase: 'betting' | 'draw' | 'showdown' | 'complete';
  pot: number;
  current_bet: number;
  active_player: number | null;
  available_actions: string[] | null;
  next_discard_player: number | null;
  betting_context?: {
    player_id: number;
    to_call: number;
    current_bet: number;
    min_bet: number;
    min_raise: number;
    stack: number;
    committed: number;
  };
  draw_context?: {
    player_id: number | null;
    max_discards: number;
    hand_size: number;
  };
  players: PlayerState[];
  events: Array<{ type: string; payload: Record<string, unknown> }>;
}

export interface PlayerState {
  player_id: number;
  name: string;
  stack: number;
  starting_stack: number;
  hand: string[];
  hand_after: string[];
  folded: boolean;
  all_in: boolean;
  is_human: boolean;
  betting_history: Array<{ action: string; amount: number; rationale: string | null; pot_after: number; stack_after: number }>;
}

export interface GameResult {
  game_id: number;
  winners: number[];
  pot: number;
  players: Array<{
    player_id: number;
    name: string;
    stack_change: number;
    initial_stack: number;
    final_stack: number;
  }>;
  bankrolls: Record<string, number>;
}

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://127.0.0.1:8000';

async function http<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const response = await fetch(input, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`API ${response.status}: ${text}`);
  }
  return response.json() as Promise<T>;
}

export async function createGame(payload: {
  seats: SeatConfig[];
  rules?: Record<string, unknown>;
  seed?: number;
  game_number?: number;
}): Promise<GameStateResponse> {
  return http<GameStateResponse>(`${BASE_URL}/api/games`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function fetchGame(gameId: string): Promise<GameStateResponse> {
  return http<GameStateResponse>(`${BASE_URL}/api/games/${gameId}`);
}

export async function postAction(gameId: string, payload: Record<string, unknown>): Promise<GameStateResponse> {
  return http<GameStateResponse>(`${BASE_URL}/api/games/${gameId}/action`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function resetGame(gameId: string, payload?: { seed?: number; game_number?: number }): Promise<GameStateResponse> {
  return http<GameStateResponse>(`${BASE_URL}/api/games/${gameId}/reset`, {
    method: 'POST',
    body: JSON.stringify(payload ?? {}),
  });
}

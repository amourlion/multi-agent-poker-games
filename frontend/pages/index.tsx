import { useState } from 'react';
import Head from 'next/head';
import { SeatConfigurator } from '../components/SeatConfigurator';
import { GameStateView } from '../components/GameStateView';
import type { GameResult, GameState, SeatConfig } from '../lib/api';
import { createGame, postAction, resetGame } from '../lib/api';

export default function HomePage() {
  const [gameId, setGameId] = useState<string | null>(null);
  const [state, setState] = useState<GameState | null>(null);
  const [result, setResult] = useState<GameResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCreate = async (seats: SeatConfig[]) => {
    setLoading(true);
    setError(null);
    try {
      const response = await createGame({ seats });
      setGameId(response.game_id);
      setState(response.state);
      setResult(response.result);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleAction = async (payload: Record<string, unknown>) => {
    if (!gameId) return;
    setLoading(true);
    setError(null);
    try {
      const response = await postAction(gameId, payload);
      setState(response.state);
      setResult(response.result);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleReset = async () => {
    if (!gameId) return;
    setLoading(true);
    setError(null);
    try {
      const response = await resetGame(gameId);
      setState(response.state);
      setResult(response.result);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Head>
        <title>Five-Card Draw Dashboard</title>
      </Head>
      <main>
        <h1>Multi-Agent Five-Card Draw</h1>
        <SeatConfigurator onSubmit={handleCreate} />
        <div className="status">
          {loading && <span>Loading…</span>}
          {error && <span className="error">{error}</span>}
          {gameId && (
            <button onClick={handleReset} disabled={loading}>
              Reset game
            </button>
          )}
        </div>
        {gameId && state && (
          <GameStateView state={state} result={result} onAction={handleAction} />
        )}
      </main>
      <style jsx>{`
        main {
          max-width: 960px;
          margin: 0 auto;
          padding: 2rem 1rem 4rem;
          display: flex;
          flex-direction: column;
          gap: 1.5rem;
        }
        .status {
          display: flex;
          align-items: center;
          gap: 1rem;
        }
        .error {
          color: #c00;
        }
        button {
          padding: 0.4rem 0.8rem;
          cursor: pointer;
        }
      `}</style>
    </>
  );
}

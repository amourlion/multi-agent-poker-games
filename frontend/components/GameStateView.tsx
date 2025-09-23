import { useEffect, useMemo, useState } from 'react';
import type { GameResult, GameState } from '../lib/api';

interface Props {
  state: GameState;
  result: GameResult | null;
  onAction: (payload: Record<string, unknown>) => void;
}

export function GameStateView({ state, result, onAction }: Props) {
  const [manualAction, setManualAction] = useState<string>('check');
  const [manualAmount, setManualAmount] = useState<number>(0);
  const [manualRationale, setManualRationale] = useState<string>('');
  const [discardInput, setDiscardInput] = useState<string>('');
  const [manualError, setManualError] = useState<string | null>(null);

  const activePlayerState = useMemo(() => {
    if (state.active_player === null) return null;
    return state.players.find((player) => player.player_id === state.active_player) ?? null;
  }, [state.active_player, state.players]);

  const nextDiscardPlayer = useMemo(() => {
    if (state.next_discard_player === null) return null;
    return state.players.find((player) => player.player_id === state.next_discard_player) ?? null;
  }, [state.next_discard_player, state.players]);

  const submitManualBet = () => {
    if (!activePlayerState) return;
    if (!bettingContext) {
      setManualError('Betting context unavailable');
      return;
    }
    let amount = manualAmount;
    if (manualAction === 'call') {
      amount = bettingContext.to_call;
    } else if (manualAction === 'bet') {
      const minimum = Math.max(bettingContext.min_bet, 1);
      if (amount < minimum) {
        setManualError(`Bet must be at least ${minimum}`);
        return;
      }
    } else if (manualAction === 'raise') {
      const minimumTotal = bettingContext.to_call + Math.max(bettingContext.min_raise, 1);
      if (amount < minimumTotal) {
        setManualError(`Raise must total at least ${minimumTotal}`);
        return;
      }
    }
    setManualError(null);
    onAction({
      type: 'bet',
      player_id: activePlayerState.player_id,
      action: manualAction,
      amount,
      rationale: manualRationale || undefined,
    });
  };

  const submitManualDiscard = () => {
    if (!nextDiscardPlayer) return;
    if (!drawContext) {
      setManualError('Draw context unavailable');
      return;
    }
    const indices = discardInput
      .split(',')
      .map((token) => token.trim())
      .filter((token) => token.length > 0)
      .map((token) => Number(token))
      .filter((value) => Number.isFinite(value));
    if (indices.length > drawContext.max_discards) {
      setManualError(`最多弃牌 ${drawContext.max_discards} 张`);
      return;
    }
    setManualError(null);
    onAction({
      type: 'discard',
      player_id: nextDiscardPlayer.player_id,
      discard_indices: indices,
      rationale: manualRationale || undefined,
    });
  };

  const canAutoRunAi =
    (state.phase === 'betting' && activePlayerState !== null && !activePlayerState.is_human) ||
    (state.phase === 'draw' && nextDiscardPlayer !== null && !nextDiscardPlayer.is_human);

  const bettingContext = state.betting_context;
  const drawContext = state.draw_context;

  const availableActions = state.available_actions ?? [];

  useEffect(() => {
    if (availableActions.length === 0) {
      setManualAction('check');
      return;
    }
    if (!availableActions.includes(manualAction)) {
      setManualAction(availableActions[0]);
    }
  }, [availableActions, manualAction]);

  useEffect(() => {
    if (!bettingContext) {
      setManualAmount(0);
      return;
    }
    if (manualAction === 'call') {
      setManualAmount(bettingContext.to_call);
    } else if (manualAction === 'bet') {
      setManualAmount(Math.max(bettingContext.min_bet, 1));
    } else if (manualAction === 'raise') {
      setManualAmount(bettingContext.to_call + Math.max(bettingContext.min_raise, 1));
    }
  }, [manualAction, bettingContext]);

  useEffect(() => {
    setManualError(null);
  }, [manualAction, manualAmount, manualRationale, discardInput, state]);

  return (
    <div className="game-state">
      <header>
        <h2>Game #{state.game_id}</h2>
        <div className="summary">
          <span>Phase: {state.phase}</span>
          <span>Pot: {state.pot}</span>
          <span>Current bet: {state.current_bet}</span>
          {state.active_player !== null && <span>Active player: #{state.active_player}</span>}
        </div>
      </header>

      <section className="players">
        {state.players.map((player) => (
          <article key={player.player_id} className={player.folded ? 'folded' : ''}>
            <h3>
              #{player.player_id} · {player.name}
            </h3>
          <p>
            Stack: {player.stack} (start {player.starting_stack}) · {player.folded ? 'FOLDED' : 'ACTIVE'}
          </p>
          <p>Hand: {player.hand.join(' ')}</p>
          {state.phase !== 'betting' && (
            <p>
              Hand after draw: {player.hand_after.join(' ')}
            </p>
          )}
            {player.betting_history.length > 0 && (
              <details>
                <summary>Betting history</summary>
                <ul>
                  {player.betting_history.map((event, idx) => (
                    <li key={idx}>
                      {event.action.toUpperCase()} — amount {event.amount}, pot {event.pot_after}
                      {event.rationale ? ` (${event.rationale})` : ''}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </article>
        ))}
      </section>

      <section className="controls">
        <button
          onClick={() => onAction({ type: 'auto_until_human' })}
          disabled={!canAutoRunAi}
        >
          Auto run AI until human turn
        </button>
        <button onClick={() => onAction({ type: 'advance' })}>
          Advance phase
        </button>
        <button onClick={() => onAction({ type: 'resolve' })} disabled={state.phase !== 'showdown'}>
          Resolve showdown
        </button>
        <button onClick={() => onAction({ type: 'auto_play' })}>Auto play remainder</button>
      </section>

      {state.phase === 'betting' && activePlayerState && activePlayerState.is_human && (
        <section className="manual-panel">
          <h3>Manual action for {activePlayerState.name}</h3>
          {bettingContext && (
            <p className="context">
              To call: {bettingContext.to_call} · Min bet: {bettingContext.min_bet} · Min raise total:{' '}
              {bettingContext.to_call + Math.max(bettingContext.min_raise, 1)}
            </p>
          )}
          <div className="manual-grid">
            <label>
              Action
              <select
                value={manualAction}
                onChange={(event) => setManualAction(event.target.value)}
              >
                {(availableActions.length > 0 ? availableActions : ['check']).map((action) => (
                  <option key={action} value={action}>
                    {action}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Amount
              <input
                type="number"
                value={manualAmount}
                onChange={(event) => setManualAmount(Number(event.target.value))}
              />
            </label>
            <label className="rationale">
              Rationale (optional)
              <input
                type="text"
                value={manualRationale}
                onChange={(event) => setManualRationale(event.target.value)}
                placeholder="e.g. protecting made hand"
              />
            </label>
            <button onClick={submitManualBet}>Submit manual bet</button>
          </div>
          {manualError && <p className="error">{manualError}</p>}
        </section>
      )}

      {state.phase === 'draw' && nextDiscardPlayer && nextDiscardPlayer.is_human && (
        <section className="manual-panel">
          <h3>Discard for {nextDiscardPlayer.name}</h3>
          {drawContext && (
            <p className="context">
              Max discards: {drawContext.max_discards} · Hand size: {drawContext.hand_size}
            </p>
          )}
          <div className="manual-grid">
            <label className="rationale">
              Indices to discard (comma separated)
              <input
                type="text"
                value={discardInput}
                onChange={(event) => setDiscardInput(event.target.value)}
                placeholder="e.g. 0,2"
              />
            </label>
            <label className="rationale">
              Rationale (optional)
              <input
                type="text"
                value={manualRationale}
                onChange={(event) => setManualRationale(event.target.value)}
                placeholder="e.g. draw to flush"
              />
            </label>
            <button onClick={submitManualDiscard}>Submit discard</button>
          </div>
        </section>
      )}

      {result && (
        <section className="result">
          <h3>Result</h3>
          <p>Pot: {result.pot}</p>
          <p>Winners: {result.winners.join(', ') || 'N/A'}</p>
          <ul>
            {result.players.map((player) => (
              <li key={player.player_id}>
                #{player.player_id} {player.name}: stack {player.initial_stack} → {player.final_stack} ({player.stack_change >= 0 ? '+' : ''}
                {player.stack_change})
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="events">
        <h3>Event log</h3>
        <ul>
          {state.events.map((event, idx) => (
            <li key={idx}>
              <strong>{event.type}</strong>
              <pre>{JSON.stringify(event.payload, null, 2)}</pre>
            </li>
          ))}
        </ul>
      </section>

      <style jsx>{`
        .summary span {
          margin-right: 1rem;
        }
        .players {
          display: grid;
          gap: 1rem;
          grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
        }
        article {
          border: 1px solid #ddd;
          border-radius: 8px;
          padding: 0.75rem;
          background: #fff;
        }
        article.folded {
          opacity: 0.6;
        }
       .controls {
         display: flex;
         gap: 0.75rem;
         margin: 1rem 0;
         flex-wrap: wrap;
       }
        .manual-panel {
          border: 1px solid #ccc;
          border-radius: 8px;
          padding: 1rem;
          background: #fafafa;
        }
        .manual-panel .context {
          margin: 0 0 0.5rem;
          color: #555;
        }
        .manual-panel .error {
          color: #c00;
        }
        .manual-grid {
          display: grid;
          gap: 0.75rem;
          grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
          align-items: end;
        }
        label {
          display: flex;
          flex-direction: column;
          gap: 0.25rem;
        }
        button {
          padding: 0.4rem 0.8rem;
          cursor: pointer;
        }
        .result,
        .events {
          margin-top: 1.5rem;
        }
        .events pre {
          background: #f5f5f5;
          padding: 0.5rem;
          overflow-x: auto;
        }
      `}</style>
    </div>
  );
}

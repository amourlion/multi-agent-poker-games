import { useState } from 'react';
import type { SeatConfig } from '../lib/api';

type Props = {
  onSubmit: (seats: SeatConfig[]) => void;
};

const defaultSeats: SeatConfig[] = [
  { name: 'Alice', type: 'llm', stack: 500, bet_mode: 'heuristic' },
  { name: 'Bob', type: 'random', stack: 400 },
  { name: 'Cara', type: 'human', stack: 400 },
];

export function SeatConfigurator({ onSubmit }: Props) {
  const [seats, setSeats] = useState<SeatConfig[]>(defaultSeats);

  const updateSeat = (index: number, changes: Partial<SeatConfig>) => {
    setSeats((prev) => prev.map((seat, idx) => (idx === index ? { ...seat, ...changes } : seat)));
  };

  const addSeat = () => {
    setSeats((prev) => [...prev, { name: `Player ${prev.length + 1}`, type: 'random', stack: 400 }]);
  };

  const removeSeat = (index: number) => {
    setSeats((prev) => prev.filter((_, idx) => idx !== index));
  };

  return (
    <div className="seat-configurator">
      <h2>Seating</h2>
      {seats.map((seat, index) => (
        <div key={index} className="seat-row">
          <input
            type="text"
            value={seat.name}
            onChange={(event) => updateSeat(index, { name: event.target.value })}
            placeholder="Name"
          />
          <select value={seat.type} onChange={(event) => updateSeat(index, { type: event.target.value as SeatConfig['type'] })}>
            <option value="random">Random</option>
            <option value="llm">LLM</option>
            <option value="human">Human</option>
          </select>
          <input
            type="number"
            value={seat.stack}
            onChange={(event) => updateSeat(index, { stack: Number(event.target.value) })}
            min={0}
          />
          {seat.type === 'llm' ? (
            <select
              value={seat.bet_mode ?? 'heuristic'}
              onChange={(event) => updateSeat(index, { bet_mode: event.target.value as 'heuristic' | 'llm' })}
            >
              <option value="heuristic">Heuristic</option>
              <option value="llm">LLM Inference</option>
            </select>
          ) : (
            <span className="bet-mode-placeholder">—</span>
          )}
          <button onClick={() => removeSeat(index)} disabled={seats.length <= 2}>
            Remove
          </button>
        </div>
      ))}
      <div className="seat-actions">
        <button onClick={addSeat}>Add Seat</button>
        <button onClick={() => onSubmit(seats)}>Create Game</button>
      </div>
      <style jsx>{`
        .seat-configurator {
          border: 1px solid #ccc;
          padding: 1rem;
          border-radius: 8px;
        }
        .seat-row {
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr)) auto;
          gap: 0.5rem;
          margin-bottom: 0.5rem;
          align-items: center;
        }
        .seat-actions {
          display: flex;
          gap: 1rem;
          justify-content: flex-end;
        }
        .bet-mode-placeholder {
          text-align: center;
          color: #888;
        }
        input,
        select {
          padding: 0.25rem 0.5rem;
        }
        button {
          padding: 0.35rem 0.75rem;
          cursor: pointer;
        }
      `}</style>
    </div>
  );
}

import { createContext, useCallback, useContext, useState } from 'react';

const STORAGE_KEY = 'ami_has_entered_goal';

function readStored(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'true';
  } catch {
    return false;
  }
}

interface HasEnteredGoalContextValue {
  hasEnteredGoal: boolean;
  setHasEnteredGoal: (value: boolean) => void;
}

const HasEnteredGoalContext = createContext<HasEnteredGoalContextValue | null>(null);

export function HasEnteredGoalProvider({ children }: { children: React.ReactNode }) {
  const [hasEnteredGoal, setState] = useState(readStored);

  const setHasEnteredGoal = useCallback((value: boolean) => {
    setState(value);
    try {
      if (value) localStorage.setItem(STORAGE_KEY, 'true');
      else localStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
  }, []);

  return (
    <HasEnteredGoalContext.Provider value={{ hasEnteredGoal, setHasEnteredGoal }}>
      {children}
    </HasEnteredGoalContext.Provider>
  );
}

export function useHasEnteredGoal(): HasEnteredGoalContextValue {
  const ctx = useContext(HasEnteredGoalContext);
  if (!ctx) throw new Error('useHasEnteredGoal must be used within HasEnteredGoalProvider');
  return ctx;
}

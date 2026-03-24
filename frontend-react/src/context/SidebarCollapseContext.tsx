import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react';

const STORAGE_KEY = 'ami_sidebar_collapsed';

interface SidebarCollapseContextValue {
  collapsed: boolean;
  setCollapsed: (value: boolean) => void;
  toggleCollapsed: () => void;
}

const SidebarCollapseContext = createContext<SidebarCollapseContextValue | null>(null);

function readStored(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

export function SidebarCollapseProvider({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsedState] = useState(readStored);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0');
    } catch {
      // ignore
    }
  }, [collapsed]);

  const setCollapsed = useCallback((value: boolean) => {
    setCollapsedState(value);
  }, []);

  const toggleCollapsed = useCallback(() => {
    setCollapsedState((c) => !c);
  }, []);

  return (
    <SidebarCollapseContext.Provider
      value={{ collapsed, setCollapsed, toggleCollapsed }}
    >
      {children}
    </SidebarCollapseContext.Provider>
  );
}

export function useSidebarCollapse(): SidebarCollapseContextValue {
  const ctx = useContext(SidebarCollapseContext);
  if (!ctx) {
    // Layouts without provider fall back to expanded
    return {
      collapsed: false,
      setCollapsed: () => {},
      toggleCollapsed: () => {},
    };
  }
  return ctx;
}

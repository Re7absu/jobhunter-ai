"use client";

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

interface AuthState {
  token: string | null;
  setToken: (t: string | null) => void;
  logout: () => void;
}

// localStorage hydration is synchronous, so the token is available once the client has mounted.
export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      setToken: (token) => set({ token }),
      logout: () => set({ token: null }),
    }),
    {
      name: "jobhunter-auth",
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({ token: s.token }),
    },
  ),
);

export interface AppFilters {
  city: string;
  category: string;
  status: string;
  minScore: string;
  company: string;
  dateFrom: string;
  dateTo: string;
}

export const defaultFilters: AppFilters = {
  city: "all",
  category: "all",
  status: "all",
  minScore: "",
  company: "",
  dateFrom: "",
  dateTo: "",
};

interface FilterState {
  filters: AppFilters;
  setFilter: <K extends keyof AppFilters>(k: K, v: AppFilters[K]) => void;
  reset: () => void;
}

export const useFilters = create<FilterState>()((set) => ({
  filters: defaultFilters,
  setFilter: (k, v) => set((s) => ({ filters: { ...s.filters, [k]: v } })),
  reset: () => set({ filters: defaultFilters }),
}));

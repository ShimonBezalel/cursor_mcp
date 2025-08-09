export type RunRow = {
  id: string;
  title?: string;
  prompt?: string;
  status?: string;
  repo?: string;
  branch?: string;
  created_at?: string;
  updated_at?: string;
  duration_seconds?: number;
  pr_url?: string;
  details_url?: string;
  raw?: any;
};
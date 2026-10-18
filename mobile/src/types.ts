export type Role =
  | "super_admin"
  | "league_organizer"
  | "club_manager"
  | "player"
  | "viewer";
export type Session = {
  token: string;
  role: Role;
  user_id: string;
  tenant_id: string;
  email: string;
  league_id?: string;
  club_id?: string;
  player_id?: string;
};
export type Settings = { server: string; league: string; club: string };
export type Fixture = {
  match_id: string;
  home: string;
  away: string;
  sport_id: string;
  status: string;
  starts_at?: string;
  venue?: string;
};
export type Standing = {
  team_id: string;
  rank: number;
  played: number;
  won: number;
  drawn: number;
  lost: number;
  points: number;
  diff: number;
  status: string;
};
export type Club = {
  club_id: string;
  name: string;
  venue: string;
  staff: { name: string; role: string }[];
  roster: {
    player_id: string;
    name: string;
    position: string;
    squad_id: string;
  }[];
};
export type Product = {
  product_id: string;
  name: string;
  description: string;
  variants: {
    variant_id: string;
    label: string;
    price_minor: number;
    stock: number;
  }[];
};
export type Score = {
  match_id: string;
  status: string;
  version: number;
  home: { team_id: string; score: number };
  away: { team_id: string; score: number };
  events: {
    event_id: string;
    type: string;
    sequence: number;
    compensated?: boolean;
  }[];
};
export type OfflineAction = {
  action_id: string;
  type: "score_event" | "roster_transfer";
  queued_at: string;
  base_version: number;
  payload: Record<string, unknown>;
};
export type QueueItem = OfflineAction & {
  scope: string;
  state: "pending" | "applied" | "rejected" | "duplicate";
  reason?: string;
};
export type SyncResult = {
  action_id: string;
  status: "applied" | "rejected" | "duplicate";
  resolution: string;
  error_code: string | null;
  server_version: number;
  processed_order: number;
  signature: string | null;
};
export type Receipt = {
  order_id: string;
  total_minor: number;
  receipt: {
    pdf_base64: string;
    signature: string;
    payload: Record<string, unknown>;
  };
};

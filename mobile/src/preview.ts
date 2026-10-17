import type { Club, Fixture, Product, Standing } from "./types";
// Explicit, read-only preview. Never mixed into authenticated caches or sent to the backend.
export const fixtures: Fixture[] = [
  {
    match_id: "preview-1",
    home: "Islamabad Falcons",
    away: "Lahore United",
    sport_id: "football",
    status: "in_progress",
    venue: "Main Ground",
    starts_at: "2026-10-17T08:00:00Z",
  },
  {
    match_id: "preview-2",
    home: "Capital Hoopers",
    away: "Rawalpindi Royals",
    sport_id: "basketball",
    status: "upcoming",
    venue: "Indoor Court",
    starts_at: "2026-10-17T10:00:00Z",
  },
  {
    match_id: "preview-3",
    home: "Northern XI",
    away: "Campus Strikers",
    sport_id: "cricket",
    status: "upcoming",
    venue: "Oval Ground",
    starts_at: "2026-10-18T05:00:00Z",
  },
];
export const standings: Standing[] = [
  "Islamabad Falcons",
  "Lahore United",
  "Campus Athletic",
  "Northern FC",
].map((team_id, i) => ({
  team_id,
  rank: i + 1,
  played: 5,
  won: 4 - i,
  drawn: i === 0 ? 1 : 0,
  lost: i,
  points: 13 - i * 3,
  diff: 8 - i * 3,
  status: i === 0 ? "clinched" : "still_possible",
}));
export const club: Club = {
  club_id: "preview-club",
  name: "Islamabad Falcons",
  venue: "FAST Main Ground · Islamabad",
  staff: [
    { name: "Hassan Ali", role: "Coach" },
    { name: "Sara Khan", role: "Manager" },
  ],
  roster: [
    {
      player_id: "p1",
      name: "Ahmed Malik",
      position: "Goalkeeper",
      squad_id: "first-team",
    },
    {
      player_id: "p2",
      name: "Bilal Ahmed",
      position: "Defender",
      squad_id: "first-team",
    },
    {
      player_id: "p3",
      name: "Usman Shah",
      position: "Forward",
      squad_id: "first-team",
    },
  ],
};
export const products: Product[] = [
  {
    product_id: "preview-jersey",
    name: "Falcons home jersey",
    description: "Match-day essentials. Club colours, all season.",
    variants: [
      {
        variant_id: "preview-M",
        label: "Medium",
        price_minor: 450000,
        stock: 1,
      },
      {
        variant_id: "preview-L",
        label: "Large",
        price_minor: 450000,
        stock: 5,
      },
    ],
  },
];

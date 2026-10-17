import React, { useRef, useState } from "react";
import { Alert, Pressable, Text, View } from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import { useApp } from "./state";
import { api } from "./api";
import { actionId, friendlyError, money } from "./domain";
import { useResource } from "./hooks";
import {
  Badge,
  Button,
  Busy,
  color,
  Empty,
  Field,
  Notice,
  Page,
  styles as s,
} from "./ui";
import * as sample from "./preview";
import type { Club, Fixture, Product, Receipt, Score, Standing } from "./types";
import { File, Paths } from "expo-file-system";
import * as Sharing from "expo-sharing";

function ErrorLine({ error }: { error: string }) {
  return error ? (
    <Text accessibilityLiveRegion="polite" style={s.error}>
      {error}
    </Text>
  ) : null;
}
function ResourceHead({
  resource,
}: {
  resource: {
    loading: boolean;
    cached: boolean;
    error: string;
    refresh: () => Promise<void>;
  };
}) {
  return (
    <>
      <View style={s.spread}>
        <Text style={s.small}>
          {resource.cached ? "Saved on this device" : "Latest available view"}
        </Text>
        {resource.loading ? (
          <Busy />
        ) : (
          <Pressable
            accessibilityRole="button"
            style={{ minHeight: 48, justifyContent: "center" }}
            onPress={() => void resource.refresh()}
          >
            <Text style={s.link}>Refresh</Text>
          </Pressable>
        )}
      </View>
      <ErrorLine error={resource.error} />
    </>
  );
}
function describe(value: string) {
  return value.replaceAll("_", " ");
}

export function LoginScreen() {
  const app = useApp(),
    [email, setEmail] = useState("viewer@nascon.test"),
    [password, setPassword] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function submit() {
    setBusy(true);
    setError("");
    try {
      await app.signIn(email, password);
      setPassword("");
      router.replace("/(tabs)");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Page
      title="Your club. Your season."
      subtitle="One place for the fixtures, people and moments that move your league."
    >
      <View style={s.hero}>
        <Badge text="Match day, made simple" />
        <Text style={s.heroTitle}>{"More play.\nLess paperwork."}</Text>
        <Text style={s.heroText}>
          Follow the table, manage your squad, and keep the game moving—even
          when the connection drops.
        </Text>
      </View>
      <View style={s.card}>
        <Text style={s.h2}>Welcome back</Text>
        <Field label="Email" value={email} onChangeText={setEmail} />
        <Field
          label="Password"
          secret
          value={password}
          onChangeText={setPassword}
        />
        <ErrorLine error={error} />
        <Button
          title={busy ? "Signing in…" : "Sign in"}
          onPress={() => void submit()}
          disabled={busy || !email || !password}
        />
        <Text style={s.small}>
          Demo accounts use Nascon@26. Sign-in requires the team backend.
        </Text>
      </View>
      <Button
        title="Explore read-only preview"
        secondary
        onPress={() => {
          app.setPreview(true);
          router.replace("/(tabs)");
        }}
      />
    </Page>
  );
}
export function HomeScreen() {
  const app = useApp();
  const role = app.preview
    ? "Preview"
    : describe(app.session?.role ?? "viewer");
  return (
    <Page title="Game on." subtitle="Your match-day command centre.">
      <View style={s.hero}>
        <Badge text="2026 / Season dashboard" />
        <Text style={s.heroTitle}>{"Stay close\nto the action."}</Text>
        <Text style={s.heroText}>
          Fixtures, standings and your club—all in one place.
        </Text>
        <Button
          title="Explore fixtures →"
          onPress={() => router.push("/(tabs)/fixtures")}
        />
      </View>
      <View style={s.row}>
        <View style={s.stat}>
          <Text style={s.statNumber}>
            {app.actions.filter((a) => a.state === "pending").length}
          </Text>
          <Text style={s.small}>Actions to sync</Text>
        </View>
        <View style={s.stat}>
          <Text style={s.label}>Your access</Text>
          <Text style={s.text}>{role}</Text>
        </View>
      </View>
      <View style={s.card}>
        <Text style={s.h2}>Around the league</Text>
        <Button
          title="League standings"
          secondary
          onPress={() => router.push("/(tabs)/standings")}
        />
        <Button
          title="Club profile & squad"
          secondary
          onPress={() => router.push("/(tabs)/club")}
        />
        <Button
          title="Club shop"
          secondary
          onPress={() => router.push("/(tabs)/store")}
        />
      </View>
      {!app.preview &&
        ["super_admin", "league_organizer"].includes(
          app.session?.role ?? "",
        ) && (
          <Button
            title="Record a scoring action"
            onPress={() => router.push("/scoring")}
          />
        )}
      {!app.preview &&
        ["super_admin", "club_manager"].includes(app.session?.role ?? "") && (
          <Button
            title="Manage your roster"
            onPress={() => router.push("/roster")}
          />
        )}
      <Button
        title={app.preview ? "Exit preview" : "Sign out"}
        secondary
        onPress={() => void app.signOut().then(() => router.replace("/"))}
      />
    </Page>
  );
}
export function FixturesScreen() {
  const a = useApp();
  const r = useResource<Fixture[]>(
    "fixtures",
    async () => {
      const v = await api.fixtures(a.settings, a.session!.token);
      if (!Array.isArray(v.fixtures))
        throw new Error("Expected fixtures array from backend.");
      return v.fixtures;
    },
    sample.fixtures,
  );
  return (
    <Page title="Fixtures" subtitle="Every match. Every moment.">
      <ResourceHead resource={r} />
      {r.data?.length
        ? r.data.map((f) => (
            <Pressable
              key={f.match_id}
              accessibilityRole="button"
              accessibilityLabel={`Open ${f.home} versus ${f.away}`}
              onPress={() =>
                router.push({
                  pathname: "/match/[id]",
                  params: { id: f.match_id },
                })
              }
              style={s.card}
            >
              <View style={s.spread}>
                <Text style={s.label}>{describe(f.sport_id)}</Text>
                <Badge text={f.status} />
              </View>
              <Text style={s.team}>{f.home}</Text>
              <Text style={s.small}>VERSUS</Text>
              <Text style={s.team}>{f.away}</Text>
              <View style={s.line} />
              <Text style={s.small}>
                {f.starts_at
                  ? new Date(f.starts_at).toLocaleString()
                  : "Time to be confirmed"}{" "}
                · {f.venue ?? "Venue to be confirmed"}
              </Text>
            </Pressable>
          ))
        : !r.loading && (
            <Empty
              title="No fixtures yet"
              detail="Matches will appear once the organizer publishes them."
            />
          )}
    </Page>
  );
}
export function StandingsScreen() {
  const a = useApp();
  const r = useResource<Standing[]>(
    `standings:${a.settings.league}`,
    async () => {
      const v = await api.standings(a.settings, a.session!.token);
      if (!Array.isArray(v.table))
        throw new Error("Expected standings table from backend.");
      return v.table;
    },
    sample.standings,
  );
  return (
    <Page
      title="The standings"
      subtitle={`Season table · ${a.preview ? "Sample league" : a.settings.league}`}
    >
      <ResourceHead resource={r} />
      <View style={s.card}>
        <View style={s.spread}>
          <Text style={s.label}>Club / played / difference</Text>
          <Text style={s.label}>Points</Text>
        </View>
        {r.data?.map((t) => (
          <View key={t.team_id} style={{ gap: 8, paddingVertical: 10 }}>
            <View style={s.row}>
              <Text style={[s.h2, { width: 22 }]}>{t.rank}</Text>
              <View style={{ flex: 1, gap: 5 }}>
                <Text style={s.text}>{t.team_id}</Text>
                <Text style={s.small}>
                  {t.played} played · {t.diff > 0 ? "+" : ""}
                  {t.diff} diff · {describe(t.status)}
                </Text>
              </View>
              <Text style={[s.h2, { fontSize: 25 }]}>{t.points}</Text>
            </View>
            <View style={s.line} />
          </View>
        ))}
        {!r.data?.length && !r.loading && (
          <Empty
            title="A fresh season"
            detail="Standings appear after your league is configured."
          />
        )}
      </View>
    </Page>
  );
}
export function ClubScreen() {
  const a = useApp();
  const r = useResource<Club>(
    `club:${a.settings.club}`,
    () => api.club(a.settings, a.session!.token),
    sample.club,
  );
  const c = r.data;
  return (
    <Page title="The club" subtitle="People behind the badge.">
      <ResourceHead resource={r} />
      {c ? (
        <>
          <View style={s.hero}>
            <Badge text="Club profile" />
            <Text style={s.heroTitle}>{c.name}</Text>
            <Text style={s.heroText}>{c.venue}</Text>
          </View>
          <View style={s.card}>
            <Text style={s.h2}>First team</Text>
            {c.roster?.map((p) => (
              <View key={p.player_id} style={s.row}>
                <View style={s.circle}>
                  <Text style={s.circleText}>
                    {p.name
                      .split(" ")
                      .map((x) => x[0])
                      .slice(0, 2)
                      .join("")}
                  </Text>
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={s.text}>{p.name}</Text>
                  <Text style={s.small}>
                    {p.position} · {p.squad_id}
                  </Text>
                </View>
              </View>
            ))}
            {!c.roster?.length && (
              <Text style={s.subtitle}>No players registered yet.</Text>
            )}
          </View>
          <View style={s.card}>
            <Text style={s.h2}>Club staff</Text>
            {c.staff?.map((p, i) => (
              <View key={i} style={s.spread}>
                <Text style={s.text}>{p.name}</Text>
                <Text style={s.small}>{p.role}</Text>
              </View>
            ))}
          </View>
        </>
      ) : (
        !r.loading && (
          <Empty
            title="No saved club profile"
            detail="Connect to load your club's details."
          />
        )
      )}
    </Page>
  );
}
export function StoreScreen() {
  const a = useApp();
  const r = useResource<Product[]>(
    "products",
    async () => {
      const v = await api.products(a.settings, a.session!.token);
      if (!Array.isArray(v.products))
        throw new Error("Expected products array from backend.");
      return v.products;
    },
    sample.products,
  );
  return (
    <Page title="Wear your colours." subtitle="The official club shop.">
      <ResourceHead resource={r} />
      {r.data?.map((p) => (
        <View key={p.product_id} style={s.card}>
          <View
            style={{
              backgroundColor: color.green,
              borderRadius: 12,
              padding: 28,
              alignItems: "center",
              gap: 8,
            }}
          >
            <Text
              style={{ color: color.lime, fontWeight: "800", letterSpacing: 4 }}
            >
              CLUB COLLECTION
            </Text>
            <Text style={{ fontSize: 52, color: "white", fontWeight: "900" }}>
              01
            </Text>
            <Text style={{ color: "white", fontWeight: "700" }}>
              HOME / 2026
            </Text>
          </View>
          <Text style={s.h2}>{p.name}</Text>
          <Text style={s.subtitle}>{p.description}</Text>
          {p.variants?.map((v) => (
            <View key={v.variant_id} style={s.spread}>
              <View style={{ flex: 1 }}>
                <Text style={s.text}>
                  {v.label} · {money(v.price_minor)}
                </Text>
                <Text style={s.small}>
                  {v.stock > 0 ? `${v.stock} available` : "Sold out"}
                </Text>
              </View>
              <Button
                title="Choose"
                disabled={v.stock <= 0 || a.preview}
                onPress={() =>
                  router.push({
                    pathname: "/checkout",
                    params: {
                      variant: v.variant_id,
                      label: `${p.name} · ${v.label}`,
                      price: String(v.price_minor),
                    },
                  })
                }
              />
            </View>
          ))}
          {a.preview && (
            <Text style={s.small}>
              Sign in to purchase from the actual catalogue.
            </Text>
          )}
        </View>
      ))}
      {!r.data?.length && !r.loading && (
        <Empty
          title="Shop opening soon"
          detail="Club merchandise will appear here."
        />
      )}
    </Page>
  );
}
export function MatchScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const a = useApp();
  const previewScore: Score = {
    match_id: id,
    status: "in_progress",
    version: 3,
    home: { team_id: "Islamabad Falcons", score: 2 },
    away: { team_id: "Lahore United", score: 1 },
    events: [{ event_id: "preview-event", type: "score", sequence: 3 }],
  };
  const r = useResource<Score>(
    `score:${id}`,
    () => api.score(a.settings, a.session!.token, id),
    previewScore,
  );
  const refresh = r.refresh;
  React.useEffect(() => {
    if (a.preview || !a.online) return;
    const timer = setInterval(() => void refresh(), 10000);
    return () => clearInterval(timer);
  }, [a.preview, a.online, refresh]);
  const v = r.data;
  return (
    <Page title="Match centre" subtitle={id} back>
      <ResourceHead resource={r} />
      {v && (
        <>
          <View style={s.card}>
            <Badge text={v.status} />
            <View style={s.row}>
              <View style={{ flex: 1, gap: 12 }}>
                <Text style={s.text}>{v.home.team_id}</Text>
                <Text style={s.score}>{v.home.score}</Text>
              </View>
              <Text style={s.label}>VS</Text>
              <View style={{ flex: 1, gap: 12, alignItems: "flex-end" }}>
                <Text style={s.text}>{v.away.team_id}</Text>
                <Text style={s.score}>{v.away.score}</Text>
              </View>
            </View>
            <Text style={s.small}>
              Refreshes every 10 seconds while connected.
            </Text>
          </View>
          <View style={s.card}>
            <Text style={s.h2}>Match timeline</Text>
            {v.events.map((e) => (
              <View key={e.event_id} style={{ gap: 5 }}>
                <Text style={s.text}>
                  {e.sequence}. {describe(e.type)}{" "}
                  {e.compensated ? "· reversed" : ""}
                </Text>
                <Text style={s.small}>{e.event_id}</Text>
              </View>
            ))}
            {!v.events.length && (
              <Text style={s.subtitle}>The timeline starts at kick-off.</Text>
            )}
          </View>
          {!a.preview &&
            ["super_admin", "league_organizer"].includes(
              a.session?.role ?? "",
            ) && (
              <Button
                title="Record score / correction"
                onPress={() =>
                  router.push({
                    pathname: "/scoring",
                    params: {
                      match: id,
                      version: String(v.version),
                      home: v.home.team_id,
                    },
                  })
                }
              />
            )}
          <Button
            title="Explore the club shop"
            secondary
            onPress={() => router.push("/(tabs)/store")}
          />
        </>
      )}
    </Page>
  );
}
export function SyncScreen() {
  const a = useApp();
  return (
    <Page
      title="Sync centre"
      subtitle="Your actions stay on this device until the server acknowledges them."
    >
      <View style={s.card}>
        <Text style={s.h2}>
          {a.actions.filter((x) => x.state === "pending").length} actions
          pending
        </Text>
        <Text style={s.subtitle}>
          Queued actions survive closing the app. Sync resumes when the team
          server becomes reachable.
        </Text>
        <ErrorLine error={a.error} />
        <Button
          title={a.syncing ? "Syncing…" : "Sync now"}
          disabled={!a.session || !a.online || a.syncing || a.preview}
          onPress={() => void a.sync()}
        />
      </View>
      {a.actions.map((item) => (
        <View key={item.action_id} style={s.card}>
          <View style={s.spread}>
            <Text style={s.h2}>
              {item.type === "score_event" ? "Match action" : "Roster action"}
            </Text>
            <Badge text={item.state} />
          </View>
          <Text style={s.small}>
            {new Date(item.queued_at).toLocaleString()}
          </Text>
          <Text style={s.small}>Reference: {item.action_id}</Text>
          {item.reason && (
            <Text style={s.text}>
              {item.state === "rejected"
                ? friendlyError(item.reason)
                : describe(item.reason)}
            </Text>
          )}
        </View>
      ))}
      {!a.actions.length && (
        <Empty
          title="All caught up"
          detail="Your pending and recently synchronized actions appear here."
        />
      )}
      <Button
        title="Clear completed history"
        secondary
        onPress={() => void a.clearHistory()}
      />
    </Page>
  );
}
export function SettingsScreen() {
  const a = useApp();
  const [server, setServer] = useState(a.settings.server),
    [league, setLeague] = useState(a.settings.league),
    [club, setClub] = useState(a.settings.club),
    [error, setError] = useState("");
  return (
    <Page
      title="Connect your team"
      subtitle="Use the backend laptop's address on your shared hotspot."
      back
    >
      <View style={s.card}>
        <Field
          label="Backend address"
          value={server}
          onChangeText={setServer}
          placeholder="http://192.168.43.10:8080"
        />
        <Text style={s.small}>
          Physical phone: laptop LAN IP. Android emulator: http://10.0.2.2:8080.
          Changing servers signs you out; old queued actions stay saved under
          their original account/server.
        </Text>
        <Field label="League ID" value={league} onChangeText={setLeague} />
        <Field label="Club ID" value={club} onChangeText={setClub} />
        <ErrorLine error={error} />
        <Button
          title="Save connection"
          onPress={() =>
            void a
              .configure({ server, league, club })
              .then(() => Alert.alert("Saved", "Connection settings updated."))
              .catch((e) => setError(e.message))
          }
        />
      </View>
      <Notice text="All mobile data comes from your team's self-hosted backend. Keep both devices on the same hotspot or router." />
    </Page>
  );
}
export function ScoringScreen() {
  const a = useApp(),
    params = useLocalSearchParams<{
      match?: string;
      version?: string;
      home?: string;
    }>();
  const [match, setMatch] = useState(params.match ?? ""),
    [version, setVersion] = useState(params.version ?? "0"),
    [team, setTeam] = useState(params.home ?? ""),
    [event, setEvent] = useState(""),
    [compensates, setCompensates] = useState(""),
    [reason, setReason] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  if (
    a.preview ||
    !["super_admin", "league_organizer"].includes(a.session?.role ?? "")
  )
    return (
      <Page title="Scoring access" back>
        <Notice text="Sign in as a League Organizer or Super-Admin to record match actions." />
      </Page>
    );
  async function submit(correction: boolean) {
    setError("");
    if (
      !match.trim() ||
      !Number.isInteger(Number(version)) ||
      Number(version) < 0 ||
      (!correction && (!team.trim() || !event.trim())) ||
      (correction && (!compensates.trim() || !reason.trim()))
    ) {
      setError(
        "Complete the action fields and enter a non-negative match version.",
      );
      return;
    }
    setBusy(true);
    try {
      await a.enqueue({
        type: "score_event",
        base_version: Number(version),
        payload: {
          event_id: actionId("evt"),
          match_id: match.trim(),
          type: correction ? "compensation" : "score",
          payload: correction
            ? { compensates: compensates.trim(), reason: reason.trim() }
            : { team_id: team.trim(), event_type: event.trim() },
        },
      });
      Alert.alert(
        "Action saved",
        a.online
          ? "Saved to the persistent queue. Synchronization will report the server result."
          : "Saved offline. It will sync when the server is reachable.",
      );
      router.push("/(tabs)/sync");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Page
      title="Record the moment"
      subtitle="Scores are append-only. Corrections reverse an earlier event."
      back
    >
      <View style={s.card}>
        <Field label="Match ID" value={match} onChangeText={setMatch} />
        <Field
          label="Last known match version"
          numeric
          value={version}
          onChangeText={setVersion}
        />
        <Field label="Team ID" value={team} onChangeText={setTeam} />
        <Field
          label="Event type from sport rules"
          value={event}
          onChangeText={setEvent}
          placeholder="e.g. goal, two_pointer, raid_point"
        />
        <ErrorLine error={error} />
        <Button
          title="Save scoring action"
          disabled={busy}
          onPress={() => void submit(false)}
        />
      </View>
      <View style={s.card}>
        <Text style={s.h2}>Correct an event</Text>
        <Field
          label="Event ID to reverse"
          value={compensates}
          onChangeText={setCompensates}
        />
        <Field label="Reason" value={reason} onChangeText={setReason} />
        <Button
          title="Save correction"
          secondary
          disabled={busy}
          onPress={() =>
            Alert.alert(
              "Reverse this event?",
              "The original event remains in the timeline.",
              [
                { text: "Cancel", style: "cancel" },
                { text: "Save correction", onPress: () => void submit(true) },
              ],
            )
          }
        />
      </View>
    </Page>
  );
}
export function RosterScreen() {
  const a = useApp();
  const [player, setPlayer] = useState(""),
    [from, setFrom] = useState(""),
    [to, setTo] = useState(""),
    [type, setType] = useState<"transfer" | "loan" | "release">("transfer"),
    [date, setDate] = useState(new Date().toISOString().slice(0, 10)),
    [loanEnd, setLoanEnd] = useState(""),
    [version, setVersion] = useState("0"),
    [reason, setReason] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  if (
    a.preview ||
    !["super_admin", "club_manager"].includes(a.session?.role ?? "")
  )
    return (
      <Page title="Roster access" back>
        <Notice text="Sign in as a Club Manager or Super-Admin to manage players." />
      </Page>
    );
  async function save() {
    setError("");
    if (
      !player.trim() ||
      !from.trim() ||
      (type !== "release" && !to.trim()) ||
      !/^\d{4}-\d{2}-\d{2}$/.test(date) ||
      !Number.isInteger(Number(version)) ||
      Number(version) < 0 ||
      !reason.trim() ||
      (type === "loan" &&
        (!/^\d{4}-\d{2}-\d{2}$/.test(loanEnd) || loanEnd <= date))
    ) {
      setError(
        "Complete all fields. Dates use YYYY-MM-DD, and loan return must be after the start.",
      );
      return;
    }
    setBusy(true);
    try {
      await a.enqueue({
        type: "roster_transfer",
        base_version: Number(version),
        payload: {
          request_id: actionId("transfer"),
          league_id: a.settings.league,
          player_id: player.trim(),
          type,
          from_squad_id: from.trim(),
          to_squad_id: type === "release" ? null : to.trim(),
          effective_date: date,
          loan_end_date: type === "loan" ? loanEnd : null,
          reason: reason.trim(),
          requested_by: a.session!.user_id,
        },
      });
      router.push("/(tabs)/sync");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Page
      title="Shape your squad"
      subtitle="Every change is recorded with who, when and why."
      back
    >
      <View style={s.row}>
        {(["transfer", "loan", "release"] as const).map((t) => (
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ selected: type === t }}
            key={t}
            style={[s.chip, type === t && s.chipSelected, { flex: 1 }]}
            onPress={() => setType(t)}
          >
            <Text style={s.text}>{t}</Text>
          </Pressable>
        ))}
      </View>
      <View style={s.card}>
        <Field label="Player ID" value={player} onChangeText={setPlayer} />
        <Field label="Current squad ID" value={from} onChangeText={setFrom} />
        {type !== "release" && (
          <Field label="Destination squad ID" value={to} onChangeText={setTo} />
        )}
        <Field label="Effective date" value={date} onChangeText={setDate} />
        {type === "loan" && (
          <Field
            label="Loan end date"
            value={loanEnd}
            onChangeText={setLoanEnd}
          />
        )}
        <Field
          label="Last known player history version"
          numeric
          value={version}
          onChangeText={setVersion}
        />
        <Field
          label="Reason for change"
          value={reason}
          onChangeText={setReason}
        />
        <ErrorLine error={error} />
        <Button
          title={busy ? "Saving…" : "Review & save action"}
          disabled={busy}
          onPress={() =>
            Alert.alert(
              "Confirm roster change",
              `Save this ${type} for ${player}? The server will validate league rules.`,
              [
                { text: "Cancel", style: "cancel" },
                { text: "Save action", onPress: () => void save() },
              ],
            )
          }
        />
      </View>
    </Page>
  );
}
export function CheckoutScreen() {
  const a = useApp(),
    params = useLocalSearchParams<{
      variant: string;
      label: string;
      price: string;
    }>();
  const [quantity, setQuantity] = useState("1"),
    [discount, setDiscount] = useState(""),
    [payment, setPayment] = useState("tok_success"),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [receipt, setReceipt] = useState<Receipt | null>(null);
  const attempt = useRef<{ fingerprint: string; id: string } | null>(null);
  async function buy() {
    setError("");
    if (!a.session || a.preview || !a.online) {
      setError("Purchases require a signed-in account and a reachable server.");
      return;
    }
    const count = Number(quantity);
    if (
      !params.variant ||
      !Number.isInteger(count) ||
      count < 1 ||
      count > 10
    ) {
      setError("Choose a variant and a quantity from 1 to 10.");
      return;
    }
    setBusy(true);
    try {
      const payload = {
        customer_id: a.session.user_id,
        items: [{ variant_id: params.variant, quantity: count }],
        discount_code: discount.trim() || null,
        payment: { token: payment },
      };
      const fingerprint = JSON.stringify(payload);
      if (attempt.current?.fingerprint !== fingerprint)
        attempt.current = { fingerprint, id: actionId("order") };
      const result = await api.checkout(a.settings, a.session.token, {
        order_id: attempt.current.id,
        ...payload,
      });
      if (!result.receipt?.pdf_base64)
        throw new Error("The server did not return the required PDF receipt.");
      setReceipt(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  async function share() {
    try {
      if (!receipt) return;
      const file = new File(
        Paths.cache,
        `receipt-${receipt.order_id.replace(/[^A-Za-z0-9_-]/g, "_")}.pdf`,
      );
      file.write(
        Uint8Array.from(atob(receipt.receipt.pdf_base64), (c) =>
          c.charCodeAt(0),
        ),
      );
      if (await Sharing.isAvailableAsync())
        await Sharing.shareAsync(file.uri, {
          mimeType: "application/pdf",
          dialogTitle: "Your club receipt",
        });
      else setError("File sharing is not available on this device.");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }
  return (
    <Page
      title={receipt ? "You’re all set." : "Your match-day kit"}
      subtitle={
        receipt
          ? "Payment confirmed by the team server."
          : "Mock payment only. No real money is charged."
      }
      back
    >
      {receipt ? (
        <View style={s.card}>
          <Badge text="Paid" />
          <Text style={s.h2}>Order {receipt.order_id}</Text>
          <Text style={s.score}>{money(receipt.total_minor)}</Text>
          <Text style={s.small}>Signed receipt generated by the server.</Text>
          <Button
            title="Open / share PDF receipt"
            onPress={() => void share()}
          />
        </View>
      ) : (
        <View style={s.card}>
          <Text style={s.h2}>{params.label ?? "Selected variant"}</Text>
          <Text style={s.subtitle}>
            {money(Number(params.price) || 0)} per item · total confirmed by
            server
          </Text>
          <Field
            label="Quantity"
            numeric
            value={quantity}
            onChangeText={setQuantity}
          />
          <Field
            label="Discount code (optional)"
            value={discount}
            onChangeText={setDiscount}
          />
          <Text style={s.label}>Mock payment outcome</Text>
          {[
            ["tok_success", "Successful payment"],
            ["tok_declined", "Simulate decline"],
            ["tok_capture_fail", "Simulate capture failure"],
          ].map(([token, label]) => (
            <Pressable
              key={token}
              accessibilityRole="radio"
              accessibilityState={{ checked: payment === token }}
              onPress={() => setPayment(token)}
              style={[s.chip, payment === token && s.chipSelected]}
            >
              <Text style={s.text}>{label}</Text>
            </Pressable>
          ))}
          <Button
            title={busy ? "Processing…" : "Confirm mock purchase"}
            disabled={busy || a.preview || !a.online}
            onPress={() => void buy()}
          />
        </View>
      )}
      <ErrorLine error={error} />
    </Page>
  );
}

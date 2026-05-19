-- ============================================================
-- Apex Garmin AI — PostgreSQL Schema
-- ============================================================
-- Estrategia: columnas clave para queries rápidos + JSONB para
-- todo el detalle rico. Nunca se pierde información.
-- ============================================================

-- ── USUARIOS ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
  id           SERIAL PRIMARY KEY,
  email        TEXT UNIQUE NOT NULL,
  email_key    TEXT UNIQUE NOT NULL,   -- abelgcanofuentes_at_hotmail_com
  display_name TEXT,
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  updated_at   TIMESTAMPTZ DEFAULT NOW()
);

-- ── SUEÑO DIARIO ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sleep_daily (
  id      SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  date    DATE    NOT NULL,

  -- Scores principales
  overall_recovery_score      NUMERIC(6,2),
  physical_recovery_score     NUMERIC(6,2),
  neural_recovery_score       NUMERIC(6,2),

  -- Arquitectura del sueño
  sleep_time_seconds          INTEGER,
  sleep_efficiency            NUMERIC(6,4),
  deep_ratio                  NUMERIC(6,4),
  rem_ratio                   NUMERIC(6,4),
  light_ratio                 NUMERIC(6,4),
  awake_ratio                 NUMERIC(6,4),
  fragmentation_index         NUMERIC(7,4),
  movement_index              NUMERIC(7,4),
  micro_arousal_score         NUMERIC(6,2),
  overnight_instability_score NUMERIC(6,2),
  architecture_stability_score NUMERIC(6,2),
  movement_spike_count        INTEGER,
  stage_transition_count      INTEGER,

  -- Recuperación cardíaca
  avg_sleep_hr                NUMERIC(5,1),
  resting_hr                  NUMERIC(5,1),

  -- Recuperación autónoma (HRV)
  avg_overnight_hrv           NUMERIC(6,2),
  hrv_recovery_score          NUMERIC(6,2),
  hrv_ramp_score              NUMERIC(6,2),
  hrv_first_half              NUMERIC(6,2),
  hrv_second_half             NUMERIC(6,2),
  autonomic_recovery_curve_score NUMERIC(6,2),

  -- Estrés nocturno
  avg_sleep_stress            NUMERIC(5,1),
  stress_load_score           NUMERIC(6,2),
  stress_spike_count          INTEGER,

  -- Respiración
  avg_respiration             NUMERIC(5,1),
  respiration_variability     NUMERIC(6,2),
  respiratory_stability_score NUMERIC(6,2),
  respiratory_irregularity_score NUMERIC(6,2),

  -- Oxigenación
  avg_spo2                    NUMERIC(5,1),
  min_spo2                    NUMERIC(5,1),
  oxygen_stability_score      NUMERIC(6,2),
  spo2_drop_count             INTEGER,

  -- Body Battery
  body_battery_start          NUMERIC(5,1),
  body_battery_end            NUMERIC(5,1),
  body_battery_change         NUMERIC(5,1),
  recharge_efficiency         NUMERIC(6,2),
  body_battery_recharge_velocity NUMERIC(8,4),

  -- Alineación circadiana
  circadian_alignment_score   NUMERIC(6,2),
  sleep_midpoint_minutes      NUMERIC(7,1),
  sleep_need_gap_minutes      INTEGER,

  -- Limitantes
  primary_limiter             TEXT,
  secondary_limiter           TEXT,
  headline                    TEXT,

  -- JSON completo (para no perder nada)
  analysis_json               JSONB,
  brief_json                  JSONB,
  brief_ai_json               JSONB,

  created_at  TIMESTAMPTZ DEFAULT NOW(),
  updated_at  TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(user_id, date)
);

-- ── DÍA DIARIO ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS day_daily (
  id      SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  date    DATE    NOT NULL,

  -- Scores principales
  overall_day_state_score     NUMERIC(6,2),
  system_strain_score         NUMERIC(6,2),
  day_capacity_score          NUMERIC(6,2),
  nervous_system_load_score   NUMERIC(6,2),
  energy_dynamics_score       NUMERIC(6,2),
  physical_load_score         NUMERIC(6,2),

  -- FC y estrés
  avg_day_hr                  NUMERIC(5,1),
  max_hr                      NUMERIC(5,1),
  hr_variability              NUMERIC(6,2),
  avg_hrv                     NUMERIC(6,2),
  avg_stress                  NUMERIC(5,1),
  max_stress                  NUMERIC(5,1),
  stress_spike_count          INTEGER,
  high_stress_count           INTEGER,
  high_stress_ratio           NUMERIC(7,4),

  -- Energía / Body Battery
  body_battery_start          NUMERIC(5,1),
  body_battery_end            NUMERIC(5,1),
  body_battery_change         NUMERIC(5,1),
  body_battery_slope          NUMERIC(8,4),
  recharge_events             INTEGER,
  crash_events                INTEGER,

  -- Actividad física
  steps                       INTEGER,
  intensity_minutes           NUMERIC(6,1),
  active_calories             NUMERIC(7,1),

  -- Recuperación
  recovery_response_score     NUMERIC(6,2),
  downshift_count             INTEGER,
  downshift_ratio             NUMERIC(6,4),

  -- Respiración diurna
  avg_respiration             NUMERIC(5,2),
  respiration_variability     NUMERIC(6,2),

  -- Carga de entrenamiento
  atl                         NUMERIC(7,2),
  ctl                         NUMERIC(7,2),
  tsb                         NUMERIC(7,2),
  tsb_label                   TEXT,

  -- Limitantes
  primary_limiter             TEXT,
  secondary_limiter           TEXT,
  headline                    TEXT,

  -- JSON completo
  analysis_json               JSONB,
  brief_ai_json               JSONB,

  created_at  TIMESTAMPTZ DEFAULT NOW(),
  updated_at  TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(user_id, date)
);

-- ── ACTIVIDADES ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS activities (
  id                  SERIAL PRIMARY KEY,
  user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  garmin_activity_id  BIGINT UNIQUE NOT NULL,

  -- Identificación
  name                TEXT,
  activity_type       TEXT,
  start_date          DATE,
  start_datetime      TIMESTAMPTZ,

  -- Volumen
  distance_km         NUMERIC(8,2),
  elevation_m         NUMERIC(7,1),
  moving_minutes      NUMERIC(7,1),
  elapsed_minutes     NUMERIC(7,1),
  calories            INTEGER,

  -- Cardíaco
  avg_hr              NUMERIC(5,1),
  max_hr              NUMERIC(5,1),

  -- Potencia (ciclismo)
  avg_power           NUMERIC(7,1),
  estimated_np        NUMERIC(7,1),
  garmin_np           NUMERIC(7,1),
  estimated_tss       NUMERIC(7,1),
  garmin_tss          NUMERIC(7,1),
  estimated_if        NUMERIC(5,3),
  garmin_if           NUMERIC(5,3),

  -- Training Effect
  aerobic_te          NUMERIC(4,2),
  anaerobic_te        NUMERIC(4,2),
  vo2max              NUMERIC(5,1),

  -- Scores del brief
  overall_score       NUMERIC(5,1),
  score_label         TEXT,

  -- JSON completo
  analysis_json       JSONB,
  brief_json          JSONB,

  created_at  TIMESTAMPTZ DEFAULT NOW(),
  updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── ÍNDICES ──────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_sleep_user_date   ON sleep_daily(user_id, date DESC);
CREATE INDEX IF NOT EXISTS idx_sleep_date        ON sleep_daily(date DESC);
CREATE INDEX IF NOT EXISTS idx_sleep_hrv         ON sleep_daily(user_id, avg_overnight_hrv);
CREATE INDEX IF NOT EXISTS idx_sleep_recovery    ON sleep_daily(user_id, overall_recovery_score);

CREATE INDEX IF NOT EXISTS idx_day_user_date     ON day_daily(user_id, date DESC);
CREATE INDEX IF NOT EXISTS idx_day_date          ON day_daily(date DESC);

CREATE INDEX IF NOT EXISTS idx_act_user_date     ON activities(user_id, start_date DESC);
CREATE INDEX IF NOT EXISTS idx_act_type          ON activities(user_id, activity_type);
CREATE INDEX IF NOT EXISTS idx_act_garmin_id     ON activities(garmin_activity_id);

-- ── TRIGGER updated_at automático ───────────────────────────
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_sleep_updated_at
  BEFORE UPDATE ON sleep_daily
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE OR REPLACE TRIGGER trg_day_updated_at
  BEFORE UPDATE ON day_daily
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE OR REPLACE TRIGGER trg_activities_updated_at
  BEFORE UPDATE ON activities
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE OR REPLACE TRIGGER trg_users_updated_at
  BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

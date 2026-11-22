# Modos de fallo: qué puede salir mal y qué hace el sistema (2026-11-22)

Fase 4 del plan maestro. Regla general: ante cualquier duda el sistema **no añade riesgo** y avisa.
Reducir posiciones siempre está permitido. Cada fila nombra la prueba automática que lo demuestra;
todas corren en cada cambio del código (`pytest`).

## Términos

- **Gateway:** programa de IBKR que debe estar abierto para enviar órdenes.
- **Conciliación:** comparar lo que el sistema cree que tiene con lo que el bróker dice.
- **Interruptor de emergencia:** archivo `data/KILL_SWITCH`; mientras exista no se abre nada nuevo.
- **Freeze:** huella de la configuración aprobada; si algo cambia sin re-congelar, no se opera.

## Datos

| Fallo | Qué hace el sistema | Prueba |
|---|---|---|
| El proveedor no responde | Alerta crítica, no hay plan, no hay órdenes. El vigía reintenta cada hora | `test_plan_loader_error_is_critical_and_no_heartbeat`, `test_plan_hecho_no_se_repite_y_el_fallido_se_reintenta` |
| Dato viejo (falta el cierre de hoy) | Bloquea riesgo nuevo; solo reducciones | `test_plan_stale_data_blocks_new_risk`, `test_freshness_blocks_stale_symbol` |
| Un ETF sin dato hoy | Ese ETF se deja como está; no se vende por un dato faltante | `test_stale_symbol_is_held_not_sold` |
| Las dos fuentes no coinciden | Aviso y bloqueo de riesgo nuevo | `test_cross_check`, `test_cross_check_prefers_raw_closes_when_both_have_them` |
| Dividendo o split | Se acredita al libro; no cuenta como descuadre | `test_shadow_book_receives_dividends_and_splits`, `test_dividend_cash_between_plan_and_execute_is_not_a_break` |

## Órdenes y bróker

| Fallo | Qué hace el sistema | Prueba |
|---|---|---|
| Gateway cerrado | No envía nada. Un aviso por sesión. Ejecuta cuando se abra, hasta 45 minutos antes del cierre | `test_gateway_down_is_alerted_not_crashed`, `test_gateway_cerrado_no_ejecuta_y_avisa` |
| El Gateway abre pero no responde | Hasta 4 intentos en la sesión y luego aviso crítico | `test_tope_de_intentos`, `test_tick_avisa_una_sola_vez_y_cuenta_intentos` |
| La corrida muere a media ejecución | **Nunca reenvía.** Toma el estado del bróker como verdad y pide revisión | `test_crashed_execute_is_never_resent` |
| La misma orden dos veces | Cada orden lleva un identificador único por día; si ya existe no se reenvía | `test_duplicate_order_ref_is_not_resent` |
| Orden sin llenar o a medias | Espera, luego pasa el resto a Adaptive; si tampoco, cancela y avisa | `test_timeout_escalates_to_adaptive_with_remainder`, `test_no_escalation_cancels` |
| El bróker rechaza la orden | Queda registrada como rechazada, con aviso | `test_broker_error_is_rejected_not_silent` |
| ETF suspendido o sin precio | La orden se omite | `test_no_midpoint_skips`, `test_rebalance_ignores_missing_price` |
| Precio lejos del cierre (dedo gordo) | Rechaza límites a más de 3 % del cierre de referencia | `test_pretrade_caps` |
| Orden demasiado grande o demasiadas | Tope por orden, por ETF (40 %) y por corrida (12) | `test_pretrade_caps`, `test_stale_reference_and_order_count` |
| Cuenta distinta a la esperada | Bloquea todo | `test_account_mismatch_blocks_everything` |
| Libro y bróker no cuadran | Activa el interruptor de emergencia y pide revisión | `test_reconcile_detects_breaks`, `test_execute_refuses_stale_pending_and_breaks` |
| Órdenes de un plan viejo | Se archivan como caducadas; no se ejecutan | `test_execute_refuses_stale_pending_and_breaks` |
| Mercado cerrado o feriado | No envía; las órdenes esperan | `test_execute_on_a_holiday_keeps_pending`, `test_sombra_y_fin_de_semana_nunca_ejecutan` |
| Apertura (spreads anchos) | Espera unos minutos tras la apertura | `test_execute_waits_until_spreads_settle_after_open` |

## Riesgo y configuración

| Fallo | Qué hace el sistema | Prueba |
|---|---|---|
| Caída mayor al límite (20 %) | Bloquea riesgo nuevo; solo reducciones | `test_loss_limits_match_backtest_risk_manager`, `test_global_blocks_still_allow_reductions` |
| Interruptor de emergencia activo | No abre nada nuevo; permite cerrar | `test_killswitch_vetoes_opens_and_allows_flatten` |
| Alguien cambió la configuración o el universo | El freeze no coincide: no se envían órdenes | `test_plan_orders_mode_without_freeze_blocks`, `test_freeze_catches_universe_file_edits` |
| Permiso de órdenes apagado | No ejecuta | `test_execute_not_permitted_without_allow_flag`, `test_execution_permission_matrix` |
| El copiloto de IA falla o tarda | No cambia órdenes nunca; tiene 45 segundos de límite | `test_copilot_opinion_is_recorded_and_never_changes_orders` |

## Operación

| Fallo | Qué hace el sistema | Prueba |
|---|---|---|
| Laptop apagada a la hora de la corrida | El vigía corre el plan o la ejecución cuando vuelve | `test_plan_perdido_se_recupera_el_fin_de_semana`, `test_ejecuta_tarde_si_se_perdio_la_hora` |
| Laptop apagada todo el horario de bolsa | Ese día se pierde; aviso de sesión perdida | `test_cerca_del_cierre_ya_no_ejecuta` |
| Dos corridas a la vez | Un candado deja pasar solo una | `test_candado_impide_dos_corridas` |
| La corrida no reporta en 30 horas | Alerta crítica del latido | `test_heartbeat_fresh_stale_missing` |
| El programa revienta | Alerta crítica con el error | `test_cli_crash_raises_critical_alert` |
| Archivo de estado dañado | Respaldo diario en zip, 30 días | `test_respaldo_guarda_solo_el_estado_y_rota` |
| Telegram caído o sin configurar | La corrida sigue; la alerta queda en `data/alerts.jsonl` | `test_alert_telegram_and_delivery_never_raises` |

## Lo que no está cubierto

- **Nada abre el Gateway ni hace la verificación en dos pasos.** Depende de una persona.
- **Sin Telegram configurado, las alertas no llegan a nadie.**
- **Poca memoria en la laptop.** Con menos de 1 GB libre una corrida puede fallar; el vigía reintenta.
- **Pérdida del disco.** El respaldo vive en la misma laptop por decisión de Adam.
- **Simulacro en vivo.** Estas pruebas usan un bróker simulado. Falta repetir una vez, con el Gateway
  real de paper: cerrarlo a media ejecución, y activar el interruptor de emergencia con posiciones.

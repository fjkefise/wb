import time
import threading
import logging
from datetime import datetime
from typing import List, Dict, Optional

from src.wb_price_monitor.logic import Monitor
from src.wb_price_monitor.config import load_config

logger = logging.getLogger(__name__)


class MonitorManager:
    """Manages background monitoring with start/stop/status control"""

    def __init__(self, config_path='config.yaml'):
        self.config = load_config(config_path)
        self.monitor = Monitor(config_path)
        self.cfg = self.config

        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._stop_flag = False
        self._selected_models: List[str] = []
        self._last_run: Optional[datetime] = None
        self._last_manual_run_ts = 0
        self._manual_check_cooldown = int(self.cfg.get('manual_check_cooldown_seconds', 1800))
        self._last_cycle_results = {
            'raw_products': 0,
            'total_models': 0,
            'checked_models': 0,
            'below_price': 0,
            'matched_products': 0,
            'evaluated_products': 0,
            'notifications': 0,
            'stopped_by_backoff': False,
            'errors': []
        }
        self._lock = threading.Lock()

    def start_all(self) -> bool:
        """Start monitoring all models"""
        with self._lock:
            if self._running:
                return False
            self._selected_models = list(self.cfg.get('models', {}).keys())
            self._running = True
            self._stop_flag = False
            self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._thread.start()
            logger.info('Started monitoring all models')
            return True

    def start_selected(self, model_keys: List[str]) -> bool:
        """Start monitoring selected models"""
        with self._lock:
            if self._running:
                return False
            valid_keys = set(self.cfg.get('models', {}).keys())
            self._selected_models = [k for k in model_keys if k in valid_keys]
            if not self._selected_models:
                return False
            self._running = True
            self._stop_flag = False
            self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._thread.start()
            logger.info(f'Started monitoring selected models: {self._selected_models}')
            return True

    def stop(self) -> bool:
        """Stop monitoring"""
        with self._lock:
            if not self._running:
                return False
            self._stop_flag = True
            self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info('Stopped monitoring')
        return True

    def is_running(self) -> bool:
        """Check if monitoring is active"""
        with self._lock:
            return self._running

    def get_selected_models(self) -> List[str]:
        """Get list of currently selected models"""
        with self._lock:
            return self._selected_models.copy()

    def run_once_all(self) -> Dict:
        """Run single check for all models"""
        results = {'products': 0, 'notifications': 0, 'errors': []}
        cooldown_remaining = self._manual_cooldown_remaining()
        if cooldown_remaining:
            results.update({
                'manual_cooldown_remaining_seconds': cooldown_remaining,
                'skipped_due_manual_cooldown': True,
            })
            self._last_cycle_results = results
            return results
        try:
            stats = self.monitor.run_once() or {}
            results.update(stats)
            results['products'] = stats.get('evaluated_products', 0)
            self._last_manual_run_ts = time.time()
        except Exception as e:
            logger.exception('Error in run_once_all')
            results['errors'].append(str(e))
        self._last_run = datetime.now()
        self._last_cycle_results = results
        return results

    def run_once_selected(self, model_keys: List[str]) -> Dict:
        """Run single check for selected models"""
        results = {'products': 0, 'notifications': 0, 'errors': []}
        cooldown_remaining = self._manual_cooldown_remaining()
        if cooldown_remaining:
            results.update({
                'manual_cooldown_remaining_seconds': cooldown_remaining,
                'skipped_due_manual_cooldown': True,
            })
            self._last_cycle_results = results
            return results
        try:
            valid_keys = set(self.cfg.get('models', {}).keys())
            models = {k: v for k, v in self.cfg.get('models', {}).items()
                     if k in model_keys and k in valid_keys}
            if not models:
                return results

            orig_models = self.monitor.cfg.get('models')
            try:
                self.monitor.cfg['models'] = models
                stats = self.monitor.run_once() or {}
            finally:
                self.monitor.cfg['models'] = orig_models

            results.update(stats)
            results['products'] = stats.get('evaluated_products', 0)
            self._last_manual_run_ts = time.time()
        except Exception as e:
            logger.exception('Error in run_once_selected')
            results['errors'].append(str(e))
        self._last_run = datetime.now()
        self._last_cycle_results = results
        return results

    def _manual_cooldown_remaining(self) -> int:
        if not self._last_manual_run_ts:
            return 0
        remaining = int(self._manual_check_cooldown - (time.time() - self._last_manual_run_ts))
        return max(0, remaining)

    def _monitor_loop(self):
        """Background monitoring loop"""
        interval = self.cfg.get('interval_seconds', 3600)
        while not self._stop_flag:
            try:
                with self._lock:
                    if not self._running or self._stop_flag:
                        break
                    selected = self._selected_models.copy()

                if selected:
                    self.run_once_selected(selected)

                # Sleep in small intervals to allow quick stopping
                for _ in range(int(interval)):
                    if self._stop_flag:
                        break
                    time.sleep(1)
            except Exception as e:
                logger.exception(f'Error in monitor loop: {e}')
                time.sleep(10)

        with self._lock:
            self._running = False

    def get_status(self) -> Dict:
        """Get current monitoring status"""
        with self._lock:
            return {
                'running': self._running,
                'models': self._selected_models.copy(),
                'interval': self.cfg.get('interval_seconds', 3600),
                'manual_cooldown_remaining': self._manual_cooldown_remaining(),
                'last_run': self._last_run.isoformat() if self._last_run else None,
                'cycle_results': self._last_cycle_results.copy()
            }

    def get_last_results(self) -> List[Dict]:
        """Get last found products"""
        limit = 15
        try:
            all_snapshots = []
            for model_key in self.cfg.get('models', {}).keys():
                snaps = self.monitor.db.last_snapshots(model_key, limit=5)
                all_snapshots.extend(snaps)
            # Sort by timestamp desc, take top 15
            all_snapshots.sort(key=lambda x: x.get('ts', 0), reverse=True)
            return all_snapshots[:limit]
        except Exception as e:
            logger.exception('Error getting last results')
            return []

    def _count_recent_products(self) -> int:
        """Count products found in last cycle"""
        try:
            now = int(time.time())
            interval = self.cfg.get('interval_seconds', 3600)
            return self.monitor.db.count_snapshots_since(
                now - interval,
                model_keys=list(self.cfg.get('models', {}).keys()),
            )
        except Exception:
            return 0

    def _count_recent_notifications(self) -> int:
        """Count notifications sent in last cycle"""
        try:
            now = int(time.time())
            interval = self.cfg.get('interval_seconds', 3600)
            count = 0
            # Count recent notifications
            with self.monitor.db.conn() as c:
                r = c.execute(
                    'SELECT COUNT(*) as cnt FROM notifications WHERE ts >= ?',
                    (now - interval,)
                ).fetchone()
                count = r['cnt'] if r else 0
            return count
        except Exception:
            return 0

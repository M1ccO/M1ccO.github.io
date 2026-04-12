"""Shared app bootstrap visual helpers.

Contains startup visual policy primitives used by both apps:
- FastTooltipStyle: faster tooltip wake-up
- build_fixed_light_palette: deterministic light theme palette
"""

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QProxyStyle, QStyle


class FastTooltipStyle(QProxyStyle):
    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QStyle.SH_ToolTip_WakeUpDelay:
            return 150
        if hint == QStyle.SH_ToolTip_FallAsleepDelay:
            return 20000
        return super().styleHint(hint, option, widget, returnData)


def build_fixed_light_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor('#eef3f8'))
    palette.setColor(QPalette.WindowText, QColor('#1f252b'))
    palette.setColor(QPalette.Base, QColor('#ffffff'))
    palette.setColor(QPalette.AlternateBase, QColor('#f6f9fc'))
    palette.setColor(QPalette.ToolTipBase, QColor('#ffffff'))
    palette.setColor(QPalette.ToolTipText, QColor('#1f252b'))
    palette.setColor(QPalette.Text, QColor('#1f252b'))
    palette.setColor(QPalette.Button, QColor('#f7fafc'))
    palette.setColor(QPalette.ButtonText, QColor('#1f252b'))
    palette.setColor(QPalette.BrightText, QColor('#ffffff'))
    palette.setColor(QPalette.Highlight, QColor('#2fa1ee'))
    palette.setColor(QPalette.HighlightedText, QColor('#ffffff'))
    palette.setColor(QPalette.Link, QColor('#2fa1ee'))
    palette.setColor(QPalette.PlaceholderText, QColor('#6c7a88'))
    return palette

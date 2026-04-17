"""
IoT Flasher + APK Builder Module (Alias for argos_iot_apk)
v1.20.5 → v2.1.3 Integration

This module re-exports all classes from argos_iot_apk for compatibility
with integration_patch.py which expects iot_apk module.
"""

from src.argos_iot_apk import IoTFlasher, APKBuilder

__all__ = ['IoTFlasher', 'APKBuilder']

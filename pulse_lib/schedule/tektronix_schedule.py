import logging
from typing import List

from .hardware_schedule import HardwareSchedule

class TektronixSchedule(HardwareSchedule):
    verbose = False

    def __init__(self, pulselib):
        if len(pulselib.digitizers) != 1:
            raise Exception('There should be 1 digitizer in pulselib. '
                            f'Found {len(pulselib.digitizers)} digitizers')
        self.awgs:List['Tektronix_AWG5014'] = list(pulselib.awg_devices.values())
        self.awg_is_slave = {awg.name:awg.name in pulselib.awg_sync for awg in self.awgs}
        # print(f'slaves: {self.awg_is_slave}')
        self.digitizer = list(pulselib.digitizers.values())[0]
        self.running = False
        self.schedule_parms = {}

    def set_schedule_parameters(self, **kwargs):
        for key,value in kwargs.items():
            self.schedule_parms[key] = value

    def set_configuration(self, params, n_waveforms):
        pass

    def load(self):
        pass

    def unload(self):
        pass

    def _trigger_instr(self):
        logging.info('trigger')
        self.digitizer.start_triggered()
        for awg in self.awgs:
            if not self.awg_is_slave[awg.name]:
                awg.force_trigger()
                
    def _get_digitizer_timeout(self):
        return self.digitizer.timeout.cache()
    
    def start(self, waveform_duration, n_repetitions, sequence_parameters):

        timeout_ms = self._get_digitizer_timeout()
        duration_ms = waveform_duration * n_repetitions * 1e-6
        if duration_ms > timeout_ms:
            logging.warning(f'Duration of sequence ({duration_ms:5.1f} ms) > digitizer timeout ({timeout_ms} ms)')

        if not self.running:
            self.running = True
            for awg in self.awgs:
                element_no = 1
                awg.set_sqel_trigger_wait(element_no)
                if self.awg_is_slave[awg.name]:
                    awg.set_sqel_loopcnt(n_repetitions, element_no)
                else:
                    awg.set_sqel_loopcnt(n_repetitions, element_no)
                awg.run_mode('SEQ')
                awg.run()

        self._trigger_instr()

        logging.info('started')

    def stop(self):
        if self.running:
            for awg in self.awgs:
                awg.stop()
                awg.all_channels_off()

        self.running = False

    def is_running(self):
        return self.running

    def close(self):
        self.stop()


class TektronixAtsSchedule(TektronixSchedule):
    def __init__(self, pulselib, acquisition_controller):
        super().__init__(pulselib)
        self.acquisition_controller = acquisition_controller
        
    
    def _get_digitizer_timeout(self):
        return self.digitizer.buffer_timeout()

    def _pre_acquire(self):
        for awg in self.awgs:
            if not self.awg_is_slave[awg.name]:
                awg.force_trigger()
            
    def _trigger_instr(self):
        logging.info('set trigger in ATS acquisition controller')
        self.acquisition_controller.pre_acquire = self._pre_acquire


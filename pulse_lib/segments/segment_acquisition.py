"""
File containing the parent class where all segment objects are derived from.
"""

import numpy as np

from pulse_lib.segments.utility.data_handling_functions import loop_controller
from pulse_lib.segments.data_classes.data_generic import data_container
from pulse_lib.segments.data_classes.data_acquisition import acquisition_data, acquisition
from pulse_lib.segments.utility.looping import loop_obj
from pulse_lib.segments.utility.setpoint_mgr import setpoint_mgr
from pulse_lib.segments.utility.measurement_ref import MeasurementRef
from pulse_lib.segments.segment_measurements import segment_measurements
from pulse_lib.segments.data_classes.data_generic import map_index

import copy

import matplotlib.pyplot as plt


class segment_acquisition():
    '''
    Class defining base function of a segment. All segment types should support all operators.
    If you make new data type, here you should buil-in in basic support to allow for general operations.

    For an example, look in the data classes files.
    '''
    def __init__(self, name, measurement_segment:segment_measurements, segment_type = 'render'):
        '''
        Args:
            name (str): name of the segment usually the channel name
            segment_type (str) : type of the segment (e.g. 'render' --> to be rendered, 'virtual'--> no not render.)
        '''
        self.type = segment_type
        self.name = name
        self._measurement_segment = measurement_segment
        self._measurement_index = 0

        # store data in numpy looking object for easy operator access.
        self.data = data_container(acquisition_data())

        # local copy of self that will be used to count up the virtual gates.
        self._pulse_data_all = None
        # data caching variable. Used for looping and so on (with a decorator approach)
        self.data_tmp = None

        # setpoints of the loops (with labels and units)
        self._setpoints = setpoint_mgr()
        self.render_mode = False

    def acquire(self, start, t_measure, ref=None, threshold=None,
                zero_on_high=False, accept_if=None):
        '''
        Adds an acquisition.
        Args:
            start (float or loopobj): start time
            t_measure (float or loopobj): measurement time
            ref (Optional[str or MeasurementRef]): optional reference to retrieve measurement by name
            threshold (Optional[float or loopobj]): optional threshold
            zero_on_high (bool): if True then result = 0 if value>threshold
        '''
        if isinstance(ref, MeasurementRef) and zero_on_high:
            ref.inverted()
        # TODO: measurements are not sorted in time. So, this works as long as they are added in right order.
        index = self._measurement_index
        self._measurement_index += 1
        self._measurement_segment.add_acquisition(self.name, index, threshold is not None,
                                                  ref=ref, accept_if=accept_if)
        self._acquire(start, t_measure, ref, threshold, zero_on_high)

    @loop_controller
    def _acquire(self, start, t_measure, ref=None, threshold=None, zero_on_high=False):
        acq = acquisition(ref, start, t_measure, threshold, zero_on_high)
        self.data_tmp.add_acquisition(acq)
        return self.data_tmp


    def _copy(self, cpy):
        cpy.type = copy.copy(self.type)
        cpy.data = copy.copy(self.data)

        # setpoints of the loops (with labels and units)
        cpy._setpoints = copy.copy(self._setpoints)

        return cpy

    @loop_controller
    def reset_time(self, time=None, extend_only = False):
        '''
        resets the time back to zero after a certain point
        Args:
            time (double) : (optional), after time to reset back to 0. Note that this is absolute time and not rescaled time.
            extend_only (bool) : will just extend the time in the segment and not reset it if set to true [do not use when composing wavoforms...].
        '''
        self.data_tmp.reset_time(time, extend_only)
        return self.data_tmp

    @loop_controller
    def wait(self, time):
        '''
        resets the time back to zero after a certain point
        Args:
            time (double) : time in ns to wait
        '''
        self.data_tmp.wait(time)
        return self.data_tmp


    @property
    def setpoints(self):
        return self._setpoints


    def __getitem__(self, *key):
        '''
        get slice or single item of this segment (note no copying, just referencing)
        Args:
            *key (int/slice object) : key of the element -- just use numpy style accessing (slicing supported)
        '''
        data_item = self.data[key[0]]
        if not isinstance(data_item, data_container):
            # If the slice contains only 1 element, then it's not a data_container anymore.
            # Put it in a data_container to maintain pulse_lib structure.
            data_item = data_container(data_item)

        # To avoid unnecessary copying of data we first slice on self, copy, and then restore data in self.
        # This trick makes the indexing operation orders faster.
        data_org = self.data
        self.data = data_item
        item = copy.copy(self)
        item.data = data_item # TODO [SdS]: make clean solution
        self.data = data_org
        return item

    def append(self, other, time = None):
        '''
        Put the other segment behind this one.
        Args:
            other (segment_single) : the segment to be appended
            time (double/loop_obj) : attach at the given time (if None, append at total_time of the segment)

        A time reset will be done after the other segment is added.
        TODO: transfer of units
        '''
        other_loopobj = loop_obj()
        other_loopobj.add_data(other.data, axis=list(range(other.data.ndim -1,-1,-1)))
        self._setpoints += other._setpoints
        self.__append(other_loopobj, time)

        return self

    @loop_controller
    def repeat(self, number):
        '''
        repeat a waveform n times.

        Args:
            number (int) : number of ties to repeat the waveform
        '''

        data_copy = copy.copy(self.data_tmp)
        for i in range(number-1):
            self.data_tmp.append(data_copy)

        return self.data_tmp

    @loop_controller
    def update_dim(self, loop_obj):
        '''
        update the dimesion of the segment by providing a loop object to it (decorator takes care of it).

        Args:
            loop_obj (loop_obj) : loop object with certain dimension to add.
        '''
        return self.data_tmp



    @loop_controller
    def __append(self, other, time):
        """
        Put the other segment behind this one (for single segment data object)

        Args:
            other (segment_single) : the segment to be appended
            time (double/loop_obj) : attach at the given time (if None, append at total_time of the segment)
        """
        if time is None:
            time = self.data_tmp.total_time


        self.data_tmp.append(other, time)
        return self.data_tmp

    @loop_controller
    def slice_time(self, start_time, stop_time):
        """
        Cuts parts out of a segment.

        Args:
            start_time (double) : effective new start time
            stop_time (double) : new ending time of the segment

        The slice_time function allows you to cut a waveform in different sizes.
        This function should be handy for debugging, example usage would be,
        You are runnning an algorithm and want to check what the measurement outcomes are though the whole algorithm.
        Pratically, you want to know
            0 -> 10ns (@10 ns still everything as expected?)
            0 -> 20ns
            0 -> ...
        This function would allow you to do that, e.g. by calling segment.cut_segment(0, lp.linspace(10,100,9))
        """
        self.data_tmp.slice_time(start_time, stop_time)
        return self.data_tmp

    # ==== getters on all_data

    @property
    def pulse_data_all(self):
        '''
        pulse data object that contains the counted op data of all the reference channels (e.g. IQ and virtual gates).
        '''
        if self._pulse_data_all is None:
            self._pulse_data_all = copy.copy(self.data)

        return self._pulse_data_all

    @property
    def shape(self):
        if self.render_mode == False:
            return self.data.shape
        else:
            return self.pulse_data_all.shape

    @property
    def ndim(self):
        if self.render_mode == False:
            return self.data.ndim
        else:
            return self.pulse_data_all.shape

    @property
    def total_time(self):
        if self.render_mode == False:
            return self.data.total_time
        else:
            return self.pulse_data_all.total_time

    def get_total_time(self, index):
        return self.total_time[map_index(index, self.shape)]

    @property
    def start_time(self):
        if self.render_mode == False:
            return self.data.start_time
        else:
            return self.pulse_data_all.start_time

    # ==== operations working on an index

    def _get_data_all_at(self, index):
        return self.pulse_data_all[map_index(index, self.shape)]

    def plot_segment(self, index = [0], render_full = True, sample_rate = 1e9):
        '''
        Args:
            index : index of which segment to plot
            render full (bool) : do full render (e.g. also get data form virtual channels). Put True if you want to see the waveshape send to the AWG.
            sample_rate (float): standard 1 Gs/s
        '''

        if render_full == True:
            pulse_data_curr_seg = self._get_data_all_at(index)
        else:
            pulse_data_curr_seg = self.data[map_index(index, self.shape)]

        y = pulse_data_curr_seg.render(sample_rate)
        x = np.linspace(0, pulse_data_curr_seg.total_time, len(y))
        # plot with dashed line
        plt.plot(x, y, '--', label=self.name)
        plt.xlabel("time (ns)")
        plt.ylabel("amplitude (mV)")
        plt.legend()

    def get_metadata(self):
        return self.data_tmp.get_metadata(self.name)
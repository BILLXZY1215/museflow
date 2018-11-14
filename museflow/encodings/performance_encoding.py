import heapq

import pretty_midi

from ..vocabulary import Vocabulary

class PerformanceEncoding:
    """An encoding of note sequences based on Magenta's PerformanceRNN.

    See https://magenta.tensorflow.org/performance-rnn.
    """

    def __init__(self, time_unit=0.01, max_shift_units=100, velocity_unit=4, errors='remove'):
        self._time_unit = time_unit
        self._max_shift_units = max_shift_units
        self._velocity_unit = velocity_unit
        self._errors = errors

        max_velocity_units = (128 + velocity_unit - 1) // velocity_unit
        self.vocabulary = Vocabulary(
            ['<pad>', '<s>', '</s>'] +
            [('NoteOn', i) for i in range(128)] +
            [('NoteOff', i) for i in range(128)] +
            [('SetVelocity', i + 1) for i in range(max_velocity_units)] +
            [('TimeShift', i + 1) for i in range(max_shift_units)])

    def encode(self, notes):
        queue = _NoteEventQueue(notes, quantization_step=self._time_unit)
        events = []

        last_t = 0
        velocity = 0
        for t, note, is_onset in queue:
            while last_t < t:
                shift_amount = min(t - last_t, max_shift_units)
                last_t += shift_amount
                events.append(('TimeShift', shift_amount))

            if is_onset:
                if velocity != note.velocity:
                    velocity = note.velocity
                    events.append(('SetVelocity', velocity // self._velocity_unit + 1))
                events.append(('NoteOn', note.pitch))
            else:
                events.append(('NoteOff', note.pitch))

        return events

    def decode(self, events):
        notes = []
        notes_on = defaultdict(list)
        error_count = 0

        t = 0
        velocity = 0
        for event, value in events:
            if event == 'TimeShift':
                t += value * self._time_unit
            elif event == 'SetVelocity':
                velocity = (value - 1) * self._velocity_unit
            elif event == 'NoteOn':
                note = pretty_midi.Note(start=t, end=None, pitch=value, velocity=velocity)
                notes.append(note)
                notes_on[value].append(note)
            elif event == 'NoteOff':
                try:
                    note = notes_on[value].pop()
                    note.end = t
                except IndexError:
                    error_count += 1

        if error_count:
            print('Warning: Encountered {} errors'.format(error_count), file=sys.stderr)

        if any(notes_on.values()):
            if self._errors == 'remove':
                print('Warning: Removing {} hanging note(s)'.format(sum(len(l) for l in notes_on.values())), file=sys.stderr)
                for notes_on_list in notes_on.values():
                    for note in notes_on_list:
                        notes.remove(note)
            else:  # 'ignore'
                print('Warning: Ignoring {} hanging note(s)'.format(sum(len(l) for l in notes_on.values())), file=sys.stderr)

        return notes


class _NoteEventQueue:
    """
    A priority queue of note onsets and offsets.

    The queue is ordered according to time and pitch.
    Offsets come before onsets that occur at the same time, unless they correspond
    to the same note.
    """

    def __init__(self, notes, quantization_step=None):
        """Initialize the queue.

        Args:
            notes: A list of `pretty_midi.Note` objects to fill the queue with.
            quantization_step: The quantization step in seconds. If `None`, no
                quantization will be performed.
        """
        self._quantization_step = quantization_step

        # Build a heap of note onsets and offsets. For now, we only add the onsets;
        # an offset is added once the corresponding onset is popped. This is an easy
        # way to make sure that we never pop the offset first.
        # Below, the ID of the Note object is used to stop the heap algorithm from
        # comparing the Note itself, which would raise an exception.
        self._heap = [(self._quantize(note.start), True, note.pitch, id(note), note)
                       for note in notes]
        heapq.heapify(self._heap)

    def pop(self):
        """Return the next event from the queue.

        Returns:
            A tuple of the form `(time, note, is_onset)` where `time` is the time of the
            event (expressed as the number of quantization steps if applicable) and `note`
            is the corresponding `Note` object.
        """
        time, is_onset, _, _, note = heapq.heappop(self._heap)
        if is_onset:
            # Add the offset to the queue
            heapq.heappush(self._heap,
                           (self._quantize(note.end), False, note.pitch, hash(note), note))

        return time, note, is_onset

    def __iter__(self):
        while len(self._heap) > 0:
            yield self.pop()

    def _quantize(self, value):
        if self._quantization_step:
            return int(value / self._quantization_step + 0.5)  # Round to nearest int
        else:
            return value

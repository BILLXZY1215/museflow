from cached_property import threaded_cached_property as cached_property
import tensorflow as tf

from .component import Component, using_scope


class RNNDecoder(Component):

    def __init__(self, cell, vocabulary, embedding_size, max_length=None, name='decoder'):
        super().__init__(name=name)

        self._cell = cell
        self._vocabulary = vocabulary
        self._output_projection = tf.layers.Dense(
            len(vocabulary), use_bias=False, name='output_projection')
        self._max_length = max_length

        with self.use_scope():
            self.embedding = tf.get_variable(
                'embedding_matrix', shape=[len(vocabulary), embedding_size])
            self._cell.build(tf.TensorShape([None, embedding_size]))
            self._output_projection.build([None, self._cell.output_size])
        self._built = True

    @using_scope
    def decode_train(self, inputs, targets, initial_state=None):
        target_weights = tf.sign(targets, name='target_weights')
        embedded_inputs = tf.nn.embedding_lookup(self.embedding, inputs)

        with tf.name_scope('decode_train'):
            if initial_state is None:
                initial_state = self._cell.zero_state(batch_size=tf.shape(inputs)[0],
                                                      dtype=tf.float32)

            sequence_length = tf.reduce_sum(target_weights, axis=1)
            rnn_outputs, _ = tf.nn.dynamic_rnn(
                self._cell,
                embedded_inputs,
                sequence_length=sequence_length,
                initial_state=initial_state)
            logits = self._output_projection(rnn_outputs)

            output = tf.contrib.seq2seq.BasicDecoderOutput(
                rnn_output=logits,
                sample_id=tf.argmax(logits, axis=-1)
            )

        with tf.name_scope('loss'):
            batch_size = tf.shape(logits)[0]
            train_xent = tf.nn.sparse_softmax_cross_entropy_with_logits(
                labels=targets,
                logits=logits)
            loss = (tf.reduce_sum(train_xent * tf.to_float(target_weights)) /
                    tf.to_float(batch_size))

        return output, loss

    @using_scope
    def decode(self, initial_state=None, max_length=None, batch_size=None,
               softmax_temperature=1., mode='greedy'):
        with tf.name_scope('decode_{}'.format(mode)):
            if batch_size is None:
                batch_size = tf.shape(initial_state)[0]
            if initial_state is None:
                initial_state = self._cell.zero_state(batch_size=batch_size,
                                                      dtype=tf.float32)

            decoder = tf.contrib.seq2seq.BasicDecoder(
                cell=self._cell,
                helper=self._make_helper(batch_size, softmax_temperature, mode),
                initial_state=initial_state,
                output_layer=self._output_projection)
            output, _, _ = tf.contrib.seq2seq.dynamic_decode(
                decoder=decoder,
                output_time_major=False,
                impute_finished=True,
                maximum_iterations=max_length or self._max_length)

        return output

    def _make_helper(self, batch_size, softmax_temperature, mode):
        helper_kwargs = {
            'embedding': self.embedding,
            'start_tokens': tf.tile([self._vocabulary.start_id], [batch_size]),
            'end_token': self._vocabulary.end_id
        }

        if mode == 'greedy':
            return tf.contrib.seq2seq.GreedyEmbeddingHelper(**helper_kwargs)
        if mode == 'sample':
            helper_kwargs['softmax_temperature'] = softmax_temperature
            return tf.contrib.seq2seq.SampleEmbeddingHelper(**helper_kwargs)

        raise ValueError('Unrecognized mode {!r}'.format(mode))

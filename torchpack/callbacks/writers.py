import os.path as osp

from torch.utils.tensorboard import SummaryWriter

from .. import distributed as dist
from ..environ import get_run_dir
from ..utils import fs, io
from ..utils.logging import logger
from ..utils.matching import NameMatcher
from .callback import Callback

__all__ = ['ConsoleWriter', 'TFEventWriter', 'JSONWriter']


class Writer(Callback):
    """
    Base class for all monitors.
    """
    def add_scalar(self, name, scalar):
        if dist.is_master() or not self.master_only:
            self._add_scalar(name, scalar)

    def _add_scalar(self, name, scalar):
        pass

    def add_image(self, name, tensor):
        if dist.is_master() or not self.master_only:
            self._add_image(name, tensor)

    def _add_image(self, name, tensor):
        pass


class ConsoleWriter(Writer):
    """
    Write scalar summaries into terminal.
    """
    master_only = True

    def __init__(self, scalars='*'):
        self.matcher = NameMatcher(patterns=scalars)
        self.scalars = dict()

    def _trigger_epoch(self):
        self._trigger()

    def _trigger(self):
        texts = []
        for name, scalar in sorted(self.scalars.items()):
            if self.matcher.match(name):
                texts.append('[{}] = {:.5g}'.format(name, scalar))
        if texts:
            logger.info('\n+ '.join([''] + texts))
        self.scalars.clear()

    def _add_scalar(self, name, scalar):
        self.scalars[name] = scalar


class TFEventWriter(Writer):
    """
    Write summaries to TensorFlow event file.
    """
    master_only = True

    def __init__(self, *, save_dir=None):
        if save_dir is None:
            save_dir = osp.join(get_run_dir(), 'tensorboard')
        self.save_dir = fs.normpath(save_dir)
        self.writer = SummaryWriter(self.save_dir)

    def _after_train(self):
        self.writer.close()

    def _add_scalar(self, name, scalar):
        self.writer.add_scalar(name, scalar, self.trainer.global_step)

    def _add_image(self, name, tensor):
        self.writer.add_image(name, tensor, self.trainer.global_step)


class JSONWriter(Writer):
    """
    Write scalar summaries to JSON file.
    """
    def __init__(self, save_dir=None):
        if save_dir is None:
            save_dir = osp.join(get_run_dir(), 'summaries')
        self.save_dir = osp.normpath(save_dir)
        self.save_fname = osp.join(fs.makedir(save_dir), 'scalars.json')

    def _before_train(self):
        self.summaries = []
        if osp.exists(self.save_fname):
            self.summaries = io.load(self.save_fname)

    def _trigger_epoch(self):
        self._trigger()

    def _trigger(self):
        try:
            io.save(self.save_fname, self.summaries)
        except (OSError, IOError):
            logger.exception(
                'Error occurred when saving JSON file "{}".'.format(
                    self.save_fname))

    def _after_train(self):
        self._trigger()

    def _add_scalar(self, name, scalar):
        self.summaries.append({
            'epoch_num': self.trainer.epoch_num,
            'global_step': self.trainer.global_step,
            'local_step': self.trainer.local_step,
            name: scalar
        })

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Copyright (c) 2020 by Inria
Authoried by Xiaoyu BIE (xiaoyu.bie@inrai.fr)
License agreement in LICENSE.txt
"""

import sys
import os
import socket
import datetime
import torch
from torch.utils import data

import librosa
from configparser import ConfigParser
from logger import get_logger
from pre.prepare_dataset import perpare_dataset
from model.vae import VAE
from model.rvae import RVAE
from model.storn import STORN
from model.vrnn import VRNN
from model.srnn import SRNN
from model.dks import DKS
from model.dsae import DSAE


from backup_simon.speech_dataset import *



# Re-write configure class, enable to distinguish betwwen upper and lower letters
class myconf(ConfigParser):
    def __init__(self,defaults=None):
        ConfigParser.__init__(self,defaults=None)
    def optionxform(self, optionstr):
        return optionstr


class BuildBasic():

    """
    Basical class for model building, including:
    - read common paramters for different models
    - define data loader
    - define loss function as a class member
    """

    def __init__(self, cfg = myconf()):

        # 1. Load config parser
        self.cfg = cfg
        self.model_name = self.cfg.get('Network', 'name')
        self.dataset_name = self.cfg.get('DataFrame', 'dataset_name')

        # 2. Get host name and date
        self.hostname = socket.gethostname()
        self.date = datetime.datetime.now().strftime("%Y-%m-%d-%Hh%M")

        # 3. Get logger type
        self.logger_type = self.cfg.getint('User', 'logger_type')

        # 4. Load STFT parameters
        self.wlen_sec = self.cfg.getfloat('STFT', 'wlen_sec')
        self.hop_percent = self.cfg.getfloat('STFT', 'hop_percent')
        self.fs = self.cfg.getint('STFT', 'fs')
        self.zp_percent = self.cfg.getint('STFT', 'zp_percent')
        self.trim = self.cfg.getboolean('STFT', 'trim')
        self.verbose = self.cfg.getboolean('STFT', 'verbose')

        # 5. Load training parameters
        self.lr = self.cfg.getfloat('Training', 'lr')
        self.epochs = self.cfg.getint('Training', 'epochs')
        self.batch_size = self.cfg.getint('Training', 'batch_size')
        self.sequence_len = self.cfg.getint('DataFrame','sequence_len')
        self.optimization  = self.cfg.get('Training', 'optimization')
        self.early_stop_patience = self.cfg.getint('Training', 'early_stop_patience')
        self.save_frequency = self.cfg.getint('Training', 'save_frequency')

        # 6. Create saved_model directory if not exist, and find dataset
        save_dir = self.cfg.get('User', 'save_dir')
        self.saved_root, self.train_data_dir, self.val_data_dir = perpare_dataset(self.dataset_name, self.hostname, save_dir)

        # 7. Choose to use gpu or cpu
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'

        # 8. Get model tag, used in loss figure and evaluation table
        if self.cfg.has_option('Network', 'tag'):
            self.tag = self.cfg.get('Network', 'tag')
        else:
            self.tag = '{}'.format(self.model_name)

        # 9. Define dataloader type
        self.get_seq = True


    def build_dataloader(self):
        # List all the data with certain suffix
        self.data_suffix = self.cfg.get('DataFrame', 'suffix')
        self.train_file_list = librosa.util.find_files(self.train_data_dir, ext=self.data_suffix)
        self.val_file_list = librosa.util.find_files(self.val_data_dir, ext=self.data_suffix)
        # Generate dataloader for pytorch
        self.num_workers = self.cfg.getint('DataFrame', 'num_workers')
        self.shuffle_file_list = self.cfg.get('DataFrame', 'shuffle_file_list')
        self.shuffle_samples_in_batch = self.cfg.get('DataFrame', 'shuffle_samples_in_batch')

        # Instranciate training dataloader
        if not self.get_seq:
            train_dataset = SpeechDatasetFrames(file_list = self.train_file_list,
                                                wlen_sec = self.wlen_sec,
                                                hop_percent = self.hop_percent,
                                                fs = self.fs,
                                                zp_percent = self.zp_percent,
                                                trim = self.trim,
                                                verbose = self.verbose,
                                                batch_size = self.batch_size,
                                                shuffle_file_list = self.shuffle_file_list,
                                                name = self.dataset_name)
        else:
            train_dataset = SpeechDatasetSequences(file_list=self.train_file_list,
                                                   sequence_len=self.sequence_len,
                                                   wlen_sec=self.wlen_sec,
                                                   hop_percent=self.hop_percent,
                                                   fs=self.fs,
                                                   zp_percent=self.zp_percent,
                                                   trim=self.trim,
                                                   verbose=self.verbose,
                                                   batch_size=self.batch_size,
                                                   shuffle_file_list=self.shuffle_file_list,
                                                   name=self.dataset_name)
        train_num = train_dataset.num_samples

        # Instanciate validation dataloader
        if not self.get_seq:
            val_dataset = SpeechDatasetFrames(file_list = self.val_file_list,
                                              wlen_sec = self.wlen_sec,
                                              hop_percent = self.hop_percent,
                                              fs = self.fs,
                                              zp_percent = self.zp_percent,
                                              trim = self.trim,
                                              verbose = self.verbose,
                                              batch_size = self.batch_size,
                                              shuffle_file_list = self.shuffle_file_list,
                                              name = self.dataset_name)
        else:
            val_dataset = SpeechDatasetSequences(file_list=self.val_file_list,
                                                 sequence_len=self.sequence_len,
                                                 wlen_sec=self.wlen_sec,
                                                 hop_percent=self.hop_percent,
                                                 fs=self.fs,
                                                 zp_percent=self.zp_percent,
                                                 trim=self.trim,
                                                 verbose=self.verbose,
                                                 batch_size=self.batch_size,
                                                 shuffle_file_list=self.shuffle_file_list,
                                                 name=self.dataset_name)
        val_num = val_dataset.num_samples

        # Create training dataloader
        train_dataloader = data.DataLoader(train_dataset, 
                                           batch_size=self.batch_size,
                                           shuffle=self.shuffle_samples_in_batch,
                                           num_workers = self.num_workers)

        # Create validation dataloader
        val_dataloader = data.DataLoader(val_dataset, 
                                         batch_size=self.batch_size,
                                         shuffle=self.shuffle_samples_in_batch,
                                         num_workers = self.num_workers)
        return train_dataloader, val_dataloader, train_num, val_num


    def get_basic_info(self):
        basic_info = []
        basic_info.append('HOSTNAME: ' + self.hostname)
        basic_info.append('Time: ' + self.date)
        basic_info.append('Training results will be saved in: ' + self.save_dir)
        basic_info.append('Device for training: ' + self.device)
        if self.device == 'cuda':
            basic_info.append('Cuda verion: {}'.format(torch.version.cuda))
        basic_info.append('Model name: {}'.format(self.model_name))
        return basic_info


class BuildVAE(BuildBasic):

    def __init__(self, cfg=myconf()):
        
        super().__init__(cfg)

        # Load special parameters for FFNN
        self.x_dim = self.cfg.getint('Network', 'x_dim')
        self.z_dim = self.cfg.getint('Network','z_dim')
        self.hidden_dim_enc = [int(i) for i in self.cfg.get('Network', 'hidden_dim_enc').split(',')]
        self.activation = eval(self.cfg.get('Network', 'activation'))
        
        # Create directory for results
        self.filename = "{}_{}_{}_z_dim={}".format(self.dataset_name, 
                                                   self.date, 
                                                   self.tag, 
                                                   self.z_dim)
        
        self.save_dir = os.path.join(self.saved_root, self.filename)
        if not(os.path.isdir(self.save_dir)):
            os.makedirs(self.save_dir)

        # Create logger
        log_file = os.path.join(self.save_dir, 'log.txt')
        logger = get_logger(log_file, self.logger_type)
        for log in self.get_basic_info():
            logger.info(log)
        logger.info('In this experiment, result will be saved in: ' + self.save_dir)
        self.logger = logger

        # Re-define data type
        self.get_seq = False

        self.build()

    def build(self):

        # Init VAE network
        self.logger.info('===== Init VAE =====')
        self.model = VAE(x_dim = self.x_dim,
                         z_dim = self.z_dim,
                         hidden_dim_enc = self.hidden_dim_enc,
                         activation = self.activation).to(self.device)
        
        # Print model information
        for log in self.model.get_info():
            self.logger.info(log)

        # Init optimizer (Adam by default)
        if self.optimization == 'adam':
            self.optimizer = torch.optim.Adam(self.model.parameters(), lr=self.lr)
        else:
            self.optimizer = torch.optim.Adam(self.model.parameters(), lr=self.lr)


class BuildRVAE(BuildBasic):

    def __init__(self, cfg = myconf()):

        super().__init__(cfg)

        ### Load special paramters for RVAE
        # General
        self.x_dim = self.cfg.getint('Network', 'x_dim')
        self.z_dim = self.cfg.getint('Network','z_dim')
        self.activation = self.cfg.get('Network', 'activation')
        self.dropout_p = self.cfg.getfloat('Network', 'dropout_p')
        # Generation
        self.bidir_h = self.cfg.getboolean('Network', 'bidir_h')
        self.dim_RNN_h = self.cfg.getint('Network', 'dim_RNN_h')
        self.num_RNN_h = self.cfg.getint('Network', 'num_RNN_h')
        # Inference
        self.bidir_g_x = self.cfg.getboolean('Network', 'bidir_g_x')
        self.dim_RNN_g_x = self.cfg.getint('Network', 'dim_RNN_g_x')
        self.num_RNN_g_x = self.cfg.getint('Network', 'num_RNN_g_x')
        self.rec_over_z = self.cfg.getboolean('Network', 'rec_over_z')
        self.dim_RNN_g_z = self.cfg.getint('Network', 'dim_RNN_g_z')
        self.num_RNN_g_z = self.cfg.getint('Network', 'num_RNN_g_z')
        self.dense_inference = [int(i) for i in self.cfg.get('Network', 'dense_inference').split(',')]
        
        ### Create directory for results
        self.filename = "{}_{}_{}_z_dim={}".format(self.dataset_name, 
                                                   self.date,
                                                   self.tag,
                                                   self.z_dim)                             
        self.save_dir = os.path.join(self.saved_root, self.filename)
        if not(os.path.isdir(self.save_dir)):
            os.makedirs(self.save_dir)

        ### Create logger
        log_file = os.path.join(self.save_dir, 'log.txt')
        logger = get_logger(log_file, self.logger_type)
        for log in self.get_basic_info():
            logger.info(log)
        logger.info('In this experiment, result will be saved in: ' + self.save_dir)
        self.logger = logger

        self.build()
    

    def build(self):
        
        # Init RVAE network
        self.logger.info('===== Init RVAE =====')
        self.model = RVAE(x_dim=self.x_dim, z_dim=self.z_dim, 
                          activation=self.activation,
                          bidir_g_x=self.bidir_g_x, 
                          dim_RNN_g_x=self.dim_RNN_g_x, num_RNN_g_x=self.num_RNN_g_x,
                          rec_over_z=self.rec_over_z, 
                          dim_RNN_g_z=self.dim_RNN_g_z, num_RNN_g_z=self.num_RNN_g_z,
                          dense_inference=self.dense_inference,
                          bidir_h=self.bidir_h, 
                          dim_RNN_h=self.dim_RNN_h, num_RNN_h=self.num_RNN_h,
                          dropout_p = self.dropout_p, device=self.device).to(self.device)
        # Print model information
        for log in self.model.get_info():
            self.logger.info(log)
            
        # Init optimizer (Adam by default)
        if self.optimization == 'adam':
            self.optimizer = torch.optim.Adam(self.model.parameters(), lr=self.lr)
        else:
            self.optimizer = torch.optim.Adam(self.model.parameters(), lr=self.lr)


class BuildSTORN(BuildBasic):

    def __init__(self, cfg=myconf()):

        super().__init__(cfg)

        ### Load parameters for STORN
        # General
        self.x_dim = self.cfg.getint('Network', 'x_dim')
        self.z_dim = self.cfg.getint('Network','z_dim')
        self.activation = self.cfg.get('Network', 'activation')
        self.dropout_p = self.cfg.getfloat('Network', 'dropout_p')
        # Generation
        self.dense_zx_h = [int(i) for i in self.cfg.get('Network', 'dense_zx_h').split(',')]
        self.dense_h_x = [int(i) for i in self.cfg.get('Network', 'dense_h_x').split(',')]
        self.dim_RNN_h = self.cfg.getint('Network', 'dim_RNN_h')
        self.num_RNN_h = self.cfg.getint('Network', 'num_RNN_h')
        # Inference
        self.dense_x_g = [int(i) for i in self.cfg.get('Network', 'dense_x_g').split(',')]
        self.dense_g_z = [int(i) for i in self.cfg.get('Network', 'dense_g_z').split(',')]
        self.dim_RNN_g = self.cfg.getint('Network', 'dim_RNN_g')
        self.num_RNN_g = self.cfg.getint('Network', 'num_RNN_g')
        
        ### Create directory for results
        self.filename = "{}_{}_{}_z_dim={}".format(self.dataset_name, 
                                                   self.date,
                                                   self.tag,
                                                   self.z_dim)
        self.save_dir = os.path.join(self.saved_root, self.filename)
        if not(os.path.isdir(self.save_dir)):
            os.makedirs(self.save_dir)

        ### Create logger
        log_file = os.path.join(self.save_dir, 'log.txt')
        logger = get_logger(log_file, self.logger_type)
        for log in self.get_basic_info():
            logger.info(log)
        logger.info('In this experiment, result will be saved in: ' + self.save_dir)
        self.logger = logger

        self.build()
    
    def build(self):

        self.logger.info('===== Init STORN =====')
        self.model = STORN(x_dim=self.x_dim, z_dim=self.z_dim, activation=self.activation,
                           dense_zx_h=self.dense_zx_h, dense_h_x=self.dense_h_x,
                           dim_RNN_h=self.dim_RNN_h, num_RNN_h=self.num_RNN_h,
                           dense_x_g=self.dense_x_g, dense_g_z=self.dense_g_z,
                           dim_RNN_g=self.dim_RNN_g, num_RNN_g=self.num_RNN_g,
                           dropout_p = self.dropout_p, device=self.device).to(self.device)
        # Print model information
        for log in self.model.get_info():
            self.logger.info(log)
            
        # Init optimizer (Adam by default)
        if self.optimization == 'adam':
            self.optimizer = torch.optim.Adam(self.model.parameters(), lr=self.lr)
        else:
            self.optimizer = torch.optim.Adam(self.model.parameters(), lr=self.lr)


class BuildVRNN(BuildBasic):

    def __init__(self, cfg=myconf()):

        super().__init__(cfg)

        ### Load parameters for VRNN
        # General
        self.x_dim = self.cfg.getint('Network', 'x_dim')
        self.z_dim = self.cfg.getint('Network','z_dim')
        self.activation = self.cfg.get('Network', 'activation')
        self.dropout_p = self.cfg.getfloat('Network', 'dropout_p')
        # Feature extractor
        self.dense_x = [int(i) for i in self.cfg.get('Network', 'dense_x').split(',')]
        self.dense_z = [int(i) for i in self.cfg.get('Network', 'dense_z').split(',')]
        # Dense layers
        self.dense_hx_z = [int(i) for i in self.cfg.get('Network', 'dense_hx_z').split(',')]
        self.dense_hz_x = [int(i) for i in self.cfg.get('Network', 'dense_hz_x').split(',')]
        self.dense_h_z = [int(i) for i in self.cfg.get('Network', 'dense_h_z').split(',')]
        # RNN
        self.dim_RNN = self.cfg.getint('Network', 'dim_RNN')
        self.num_RNN = self.cfg.getint('Network', 'num_RNN')

        ### Create directory for results
        self.filename = "{}_{}_{}_z_dim={}".format(self.dataset_name, 
                                                   self.date,
                                                   self.tag,
                                                   self.z_dim)
        self.save_dir = os.path.join(self.saved_root, self.filename)
        if not(os.path.isdir(self.save_dir)):
            os.makedirs(self.save_dir)                                              

        ### Create logger
        log_file = os.path.join(self.save_dir, 'log.txt')
        logger = get_logger(log_file, self.logger_type)
        for log in self.get_basic_info():
            logger.info(log)
        logger.info('In this experiment, result will be saved in: ' + self.save_dir)
        self.logger = logger

        self.build()

    def build(self):
        # Init RVAE network
        self.logger.info('===== Init VRNN =====')
        self.model = VRNN(x_dim=self.x_dim, z_dim=self.z_dim, 
                          activation=self.activation,
                          dense_x=self.dense_x, dense_z=self.dense_z,
                          dense_hx_z=self.dense_hx_z, dense_hz_x=self.dense_hz_x, 
                          dense_h_z=self.dense_h_z,
                          dim_RNN=self.dim_RNN, num_RNN=self.num_RNN,
                          dropout_p = self.dropout_p,
                          device=self.device).to(self.device)
        # Print model information
        for log in self.model.get_info():
            self.logger.info(log)
            
        # Init optimizer (Adam by default)
        if self.optimization == 'adam':
            self.optimizer = torch.optim.Adam(self.model.parameters(), lr=self.lr)
        else:
            self.optimizer = torch.optim.Adam(self.model.parameters(), lr=self.lr)


class BuildSRNN(BuildBasic):

    def __init__(self, cfg=myconf()):

        super().__init__(cfg)

        ### Load parameters for SRNN
        # General
        self.x_dim = self.cfg.getint('Network', 'x_dim')
        self.z_dim = self.cfg.getint('Network','z_dim')
        self.activation = self.cfg.get('Network', 'activation')
        self.dropout_p = self.cfg.getfloat('Network', 'dropout_p')
        # Dense layers
        self.dense_x_h = [int(i) for i in self.cfg.get('Network', 'dense_x_h').split(',')] if self.cfg.has_option('Network', 'dense_x_h') else []
        self.dense_hx_g = [int(i) for i in self.cfg.get('Network', 'dense_hx_g').split(',')] if self.cfg.has_option('Network', 'dense_hx_g') else []
        self.dense_gz_z = [int(i) for i in self.cfg.get('Network', 'dense_gz_z').split(',')]
        self.dense_hz_x = [int(i) for i in self.cfg.get('Network', 'dense_hz_x').split(',')]
        self.dense_hz_z = [int(i) for i in self.cfg.get('Network', 'dense_hz_z').split(',')]
        # RNN
        self.dim_RNN_h = self.cfg.getint('Network', 'dim_RNN_h')
        self.num_RNN_h = self.cfg.getint('Network', 'num_RNN_h')
        self.dim_RNN_g = self.cfg.getint('Network', 'dim_RNN_g')
        self.num_RNN_g = self.cfg.getint('Network', 'num_RNN_g')
        
        ### Create direcotry for results
        self.filename = "{}_{}_{}_z_dim={}".format(self.dataset_name, 
                                                      self.date,
                                                      self.tag,
                                                      self.z_dim)
        self.save_dir = os.path.join(self.saved_root, self.filename)
        if not(os.path.isdir(self.save_dir)):
            os.makedirs(self.save_dir)

        ### Create logger
        log_file = os.path.join(self.save_dir, 'log.txt')
        logger = get_logger(log_file, self.logger_type)
        for log in self.get_basic_info():
            logger.info(log)
        logger.info('In this experiment, result will be saved in: ' + self.save_dir)
        self.logger = logger

        self.build()

    def build(self):

        self.logger.info('===== Init SRNN =====')
        self.model = SRNN(x_dim=self.x_dim, z_dim=self.z_dim, 
                          activation=self.activation,
                          dense_x_h=self.dense_x_h,
                          dense_hx_g=self.dense_hx_g,
                          dense_gz_z=self.dense_gz_z,
                          dense_hz_x=self.dense_hz_x,
                          dense_hz_z=self.dense_hz_z,
                          dim_RNN_h=self.dim_RNN_h,
                          num_RNN_h=self.num_RNN_h,
                          dim_RNN_g=self.dim_RNN_g,
                          num_RNN_g=self.num_RNN_g,
                          dropout_p = self.dropout_p,
                          device=self.device).to(self.device)
        # Print model information
        for log in self.model.get_info():
            self.logger.info(log)
            
        # Init optimizer (Adam by default)
        if self.optimization == 'adam':
            self.optimizer = torch.optim.Adam(self.model.parameters(), lr=self.lr)
        else:
            self.optimizer = torch.optim.Adam(self.model.parameters(), lr=self.lr)


class BuildDKS(BuildBasic):

    def __init__(self, cfg=myconf()):

        super().__init__(cfg)

        ### Load parameters for SRNN
        # General
        self.x_dim = self.cfg.getint('Network', 'x_dim')
        self.z_dim = self.cfg.getint('Network','z_dim')
        self.activation = self.cfg.get('Network', 'activation')
        self.dropout_p = self.cfg.getfloat('Network', 'dropout_p')
        # Generation
        self.dense_z_x = [int(i) for i in self.cfg.get('Network', 'dense_z_x').split(',')]
        # Inference
        self.dim_RNN_g = self.cfg.getint('Network', 'dim_RNN_g')
        self.num_RNN_g = self.cfg.getint('Network', 'num_RNN_g')
        self.bidir_g = self.cfg.getboolean('Network', 'bidir_g')
        # Prior
        self.dense_z_z = [int(i) for i in self.cfg.get('Network', 'dense_z_z').split(',')]

        ### Create direcotry for results
        self.filename = "{}_{}_{}_z_dim={}".format(self.dataset_name, 
                                                   self.date,
                                                   self.tag,
                                                   self.z_dim)
        self.save_dir = os.path.join(self.saved_root, self.filename)
        if not(os.path.isdir(self.save_dir)):
            os.makedirs(self.save_dir)

        ### Create logger
        log_file = os.path.join(self.save_dir, 'log.txt')
        logger = get_logger(log_file, self.logger_type)
        for log in self.get_basic_info():
            logger.info(log)
        logger.info('In this experiment, result will be saved in: ' + self.save_dir)
        self.logger = logger

        self.build()

    def build(self):

        self.logger.info('===== Init DKS =====')
        self.model = DKS(x_dim=self.x_dim, z_dim=self.z_dim, 
                         activation=self.activation,
                         dense_z_x=self.dense_z_x,
                         dim_RNN_g=self.dim_RNN_g, num_RNN_g=self.num_RNN_g,
                         bidir_g=self.bidir_g,
                         dense_z_z=self.dense_z_z,
                         dropout_p = self.dropout_p, device=self.device).to(self.device)
        # Print model information
        for log in self.model.get_info():
            self.logger.info(log)
            
        # Init optimizer (Adam by default)
        if self.optimization == 'adam':
            self.optimizer = torch.optim.Adam(self.model.parameters(), lr=self.lr)
        else:
            self.optimizer = torch.optim.Adam(self.model.parameters(), lr=self.lr)


class BuildDSAE(BuildBasic):
    
    def __init__(self, cfg=myconf()):

        super().__init__(cfg)

        ### Load special parameters for DSAE
        # General
        self.x_dim = self.cfg.getint('Network', 'x_dim')
        self.z_dim = self.cfg.getint('Network','z_dim')
        self.v_dim = self.cfg.getint('Network','v_dim')
        self.activation = self.cfg.get('Network', 'activation')
        self.dropout_p = self.cfg.getfloat('Network', 'dropout_p')
        # Generation
        self.dense_vz_x = [int(i) for i in self.cfg.get('Network', 'dense_vz_x').split(',')]
        # Inference
        self.dim_RNN_gv = self.cfg.getint('Network', 'dim_RNN_gv')
        self.num_RNN_gv = self.cfg.getint("Network", 'num_RNN_gv')
        self.bidir_gv = self.cfg.getboolean('Network', 'bidir_gv')
        self.dim_RNN_gx = self.cfg.getint('Network', 'dim_RNN_gx')
        self.num_RNN_gx = self.cfg.getint('Network', 'num_RNN_gx')
        self.bidir_gx = self.cfg.getboolean('Network', 'bidir_gx')
        self.dim_RNN_total = self.cfg.getint('Network', 'dim_RNN_total')
        self.num_RNN_total = self.cfg.getint('Network', 'num_RNN_total')
        self.bidir_total = self.cfg.getboolean('Network', 'bidir_total')
        # Prior
        self.dim_RNN_prior = self.cfg.getint('Network', 'dim_RNN_prior')
        self.num_RNN_prior = self.cfg.getint('Network', 'num_RNN_prior')
        self.bidir_prior = self.cfg.getboolean('Network', 'bidir_prior')

        #### Create directory for results
        self.filename = "{}_{}_{}z_dim={}".format(self.dataset_name,
                                                  self.date,
                                                  self.tag,
                                                  self.z_dim)
        self.save_dir = os.path.join(self.saved_root, self.filename)
        if not(os.path.isdir(self.save_dir)):
            os.makedirs(self.save_dir)

        #### Create logger
        log_file = os.path.join(self.save_dir, 'log.txt')
        logger = get_logger(log_file, self.logger_type)
        for log in self.get_basic_info():
            logger.info(log)
        logger.info("In this experiment, result will be saved in: " + self.save_dir)
        self.logger = logger
        
        self.build()


    def build(self):

        # Init DSAE network
        self.logger.info('==== Init DSAE ====')
        self.model = DSAE(x_dim=self.x_dim, z_dim=self.z_dim, v_dim=self.v_dim,
                          activation=self.activation,
                          dense_vz_x=self.dense_vz_x,
                          dim_RNN_gv=self.dim_RNN_gv, num_RNN_gv=self.num_RNN_gv,
                          bidir_gv=self.bidir_gv,
                          dim_RNN_gx=self.dim_RNN_gx, num_RNN_gx=self.num_RNN_gx,
                          bidir_gx=self.bidir_gx,
                          dim_RNN_total=self.dim_RNN_total, num_RNN_total=self.num_RNN_total,
                          bidir_total=self.bidir_total,
                          dim_RNN_prior=self.dim_RNN_prior, num_RNN_prior=self.num_RNN_prior,
                          bidir_prior=self.bidir_prior,
                          dropout_p = self.dropout_p, device=self.device).to(self.device)
        # Print model information
        for log in self.model.get_info():
            self.logger.info(log)

        # Init optimizer (Adam by default):
        if self.optimization == 'adam':
            self.optimizer = torch.optim.Adam(self.model.parameters(), lr=self.lr)
        else:
            self.optimizer = torch.optim.Adam(self.model.parameters(), lr=self.lr)



def build_model(config_file='config_default.ini'):
    if not os.path.isfile(config_file):
        raise ValueError('Invalid config file path')    
    cfg = myconf()
    cfg.read(config_file)
    model_name = cfg.get('Network', 'name')
    if model_name == 'VAE':
        model_class = BuildVAE(cfg)
    elif model_name == 'RVAE':
        model_class = BuildRVAE(cfg)
    elif model_name == 'STORN':
        model_class = BuildSTORN(cfg)
    elif model_name == 'VRNN':
        model_class = BuildVRNN(cfg)
    elif model_name == 'SRNN':
        model_class = BuildSRNN(cfg)
    elif model_name == 'DKS':
        model_class = BuildDKS(cfg)
    elif model_name == 'DSAE':
        model_class = BuildDSAE(cfg)
    return model_class


if __name__ == '__main__':
    model_class = build_model('config/cfg_debug_srnn.ini')
    model = model_class.model
    optimizer = model_class.optimizer
    train_dataloader, _, _, _ = model_class.build_dataloader()

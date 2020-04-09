#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Copyright (c) 2020 by Inria
Authoried by Xiaoyu BIE (xiaoyu.bie@inrai.fr)
License agreement in LICENSE.txt

The code in this file is based on:
- “A Recurrent Latent Variable Model for Sequential Data” ICLR, 2015
"""

from torch import nn
import numpy as np
import torch
from collections import OrderedDict


class VRNN(nn.Module):

    def __init__(self, x_dim, z_dim=16, activation = 'relu',
                 hidden_x=[128], hidden_z=[128],
                 hidden_enc=[128], hidden_dec=[128], hidden_prior=[128],
                 h_dim=128, num_LSTM=1,
                 dropout_p = 0, device='cpu'):

        super().__init__()
        ### General parameters for vrnn
        self.x_dim = x_dim
        self.z_dim = z_dim
        self.dropout_p = dropout_p
        self.y_dim = self.x_dim
        if activation == 'relu':
            self.activation = nn.ReLU()
        elif activation == 'tanh':
            self.activation = nn.Tanh()
        else:
            raise SystemExit('Wrong activation type!')
        self.device = device
        ### Feature extractors parameters
        self.hidden_x = hidden_x
        self.hidden_z = hidden_z
        #### Dense layers (encode, decode and prior) parameters
        self.hidden_enc = hidden_enc
        self.hidden_dec = hidden_dec
        self.hidden_prior = hidden_prior
        ### Encoder parameters


        ### Recurrence parameters
        self.h_dim = h_dim
        self.num_LSTM = num_LSTM
        ### Decoder parameters

        self.build()

    def build(self):
        #### Feature extractor
        # x
        dic_layers = OrderedDict()
        for n in range(len(self.hidden_x)):
            if n == 0:
                dic_layers['linear'+str(n)] = nn.Linear(self.x_dim, self.hidden_x[n])
            else:
                dic_layers['linear'+str(n)] = nn.Linear(self.hidden_x[n-1], self.hidden_x[n])
            dic_layers['activation'+str(n)] = self.activation
            dic_layers['dropout'+str(n)] = nn.Dropout(p=self.dropout_p)
        self.feature_extractor_x = nn.Sequential(dic_layers)
        # z
        dic_layers = OrderedDict()
        for n in range(len(self.hidden_z)):
            if n == 0:
                dic_layers['linear'+str(n)] = nn.Linear(self.z_dim, self.hidden_z[n])
            else:
                dic_layers['linear'+str(n)] = nn.Linear(self.hidden_z[n-1], self.hidden_z[n])
            dic_layers['activation'+str(n)] = self.activation
            dic_layers['dropout'+str(n)] = nn.Dropout(p=self.dropout_p)
        self.feature_extractor_z = nn.Sequential(dic_layers)
        
        ### Dense layers (encode, decode and prior) 
        # encode
        dic_layers = OrderedDict()
        for n in range(len(self.hidden_enc)):
            if n == 0:
                dic_layers['linear'+str(n)] = nn.Linear(self.hidden_x[-1] + self.h_dim, self.hidden_enc[n])
            else:
                dic_layers['linear'+str(n)] = nn.Linear(self.hidden_enc[n-1], self.hidden_enc[n])
            dic_layers['activation'+str(n)] = self.activation
            dic_layers['dropout'+str(n)] = nn.Dropout(p=self.dropout_p)
        self.enc_dense = nn.Sequential(dic_layers)
        self.enc_mean = nn.Linear(self.hidden_enc[-1], self.z_dim)
        self.enc_logvar = nn.Linear(self.hidden_enc[-1], self.z_dim)
        # decode
        dic_layers = OrderedDict()
        for n in range(len(self.hidden_dec)):
            if n == 0:
                dic_layers['linear'+str(n)] = nn.Linear(self.hidden_z[-1] + self.h_dim, self.hidden_dec[n])
            else:
                dic_layers['linear'+str(n)] = nn.Linear(self.hidden_dec[n-1], self.hidden_dec[n])
            dic_layers['activation'+str(n)] = self.activation
            dic_layers['dropout'+str(n)] = nn.Dropout(p=self.dropout_p)
        self.dec_dense = nn.Sequential(dic_layers)
        self.dec_logvar = nn.Linear(self.hidden_dec[-1], self.y_dim)
        # prior
        dic_layers = OrderedDict()
        for n in range(len(self.hidden_prior)):
            if n == 0:
                dic_layers['linear'+str(n)] = nn.Linear(self.h_dim, self.hidden_prior[n])
            else:
                dic_layers['linear'+str(n)] = nn.Linear(self.hidden_prior[n-1], self.hidden_prior[n])
            dic_layers['activation'+str(n)] = self.activation
            dic_layers['dropout'+str(n)] = nn.Dropout(p=self.dropout_p)
        self.prior_dense = nn.Sequential(dic_layers)
        self.prior_mean = nn.Linear(self.hidden_prior[-1], self.z_dim)
        self.prior_logvar = nn.Linear(self.hidden_prior[-1], self.z_dim)
        
        #### Recurrent layer
        self.rnn = nn.LSTM(self.hidden_x[-1]+self.hidden_z[-1], self.h_dim, self.num_LSTM, bidirectional=False)

    def inference(self, feature_xt, h_t):
        enc_input = torch.cat((feature_xt, h_t), 2)
        enc_output = self.enc_dense(enc_input)
        mean_zt = self.enc_mean(enc_output)
        logvar_zt = self.enc_logvar(enc_output)
        return mean_zt, logvar_zt

    def generation(self, feature_zt, h_t):
        dec_input = torch.cat((feature_zt, h_t), 2)
        dec_output = self.dec_dense(dec_input)
        log_yt = self.dec_logvar(dec_output)
        return log_yt

    def recurrence(self, feature_xt, feature_zt, h_t, c_t):
        rnn_input = torch.cat((feature_xt, feature_zt), 2)
        _, (h_tp1, c_tp1) = self.rnn(rnn_input, (h_t, c_t))
        return h_tp1, c_tp1

    def prior(self, h):
        prior_output = self.prior_dense(h)
        mean_prior = self.enc_mean(prior_output)
        logvar_prior = self.enc_logvar(prior_output)
        return mean_prior, logvar_prior

    def reparatemize(self, mean, std):
        eps = torch.randn_like(std)
        return eps.mul(std).add_(mean)

    def forward(self, x):
        # case1: input x is (batch_size, x_dim, seq_len)
        #        we want to change it to (seq_len, batch_size, x_dim)
        # case2: shape of x is (seq_len, x_dim) but we need 
        #        (seq_len, batch_size, x_dim)
        if len(x.shape) == 3:
            x = x.permute(-1, 0, 1)
        elif len(x.shape) == 2:
            x = x.unsqueeze(1)

        # print('shape of input: {}'.format(x.shape)) # used for debug only
        # input('stop')
        seq_len = x.shape[0]
        batch_size = x.shape[1]
        x_dim = x.shape[2]

        # create variable holder and send to GPU if needed
        all_enc_logvar = torch.zeros((seq_len, batch_size, self.z_dim)).to(self.device)
        all_enc_mean = torch.zeros((seq_len, batch_size, self.z_dim)).to(self.device)
        y = torch.zeros((seq_len, batch_size, self.y_dim)).to(self.device)
        z = torch.zeros((seq_len, batch_size, self.z_dim)).to(self.device)
        h = torch.zeros((seq_len, batch_size, self.h_dim)).to(self.device)
        z_t = torch.zeros(batch_size, self.z_dim).to(self.device)
        h_t = torch.zeros(self.num_LSTM, batch_size, self.h_dim).to(self.device)
        c_t = torch.zeros(self.num_LSTM, batch_size, self.h_dim).to(self.device)

        feature_x = self.feature_extractor_x(x)
        for t in range(seq_len):
            feature_xt = feature_x[t,:,:].unsqueeze(0)
            h_t_last = h_t.view(self.num_LSTM, 1, batch_size, self.h_dim)[-1,:,:,:]
            mean_zt, logvar_zt = self.inference(feature_xt, h_t_last)
            std_zt = torch.exp(0.5*logvar_zt)
            z_t = self.reparatemize(mean_zt, std_zt)
            feature_zt = self.feature_extractor_z(z_t)
            log_yt = self.generation(feature_zt, h_t_last)
            y_t = torch.exp(log_yt)
            all_enc_mean[t,:,:] = mean_zt
            all_enc_logvar[t,:,:] = logvar_zt
            z[t,:,:] = torch.squeeze(z_t)
            y[t,:,:] = torch.squeeze(y_t)
            h[t,:,:] = torch.squeeze(h_t_last)
            h_t, c_t = self.recurrence(feature_xt, feature_zt, h_t, c_t) # actual index is t+1 
        # calculate the prior
        mean_prior, logvar_prior = self.prior(h)
        
        # y/z is (seq_len, batch_size, y/z_dim), we want to change back to
        # (batch_size, y/z_dim, seq_len)
        mean = torch.squeeze(all_enc_mean)
        logvar = torch.squeeze(all_enc_logvar)
        mean_prior = torch.squeeze(mean_prior)
        logvar_prior = torch.squeeze(logvar_prior)
        z = torch.squeeze(z)
        y = torch.squeeze(y)
        if len(z.shape) == 3:
            z = z.permute(1,-1,0)
        if len(y.shape) == 3:    
            y = y.permute(1,-1,0)
        return y, mean, logvar, mean_prior, logvar_prior, z


    def get_info(self):
        info = []
        info.append("----- Feature extractor -----")
        for layer in self.feature_extractor_x:
            info.append(str(layer))
        for layer in self.feature_extractor_z:
            info.append(str(layer))
        info.append("----- Inference -----")
        for layer in self.enc_dense:
            info.append(str(layer))
        info.append(str(self.enc_mean))
        info.append(str(self.enc_logvar))
        info.append("----- Generation -----")
        for layer in self.dec_dense:
            info.append(str(layer))
        info.append(str(self.dec_logvar))
        info.append("----- Recurrence -----")
        info.append(str(self.rnn))
        info.append("----- Prior -----")
        for layer in self.prior_dense:
            info.append(str(layer))
        info.append(str(self.prior_mean))
        info.append(str(self.prior_logvar))

        return info


if __name__ == '__main__':
    x_dim = 513
    z_dim = 16
    device = 'cpu'
    vrnn = VRNN(x_dim=x_dim, z_dim=z_dim).to(device)
    model_info = vrnn.get_info()
    # for i in model_info:
    #     print(i)

    x = torch.ones((2,513,3))
    y, mean, logvar, mean_prior, logvar_prior, z = vrnn.forward(x)
    print(x.shape)
    print(y.shape)
    print(mean.shape)
    print(logvar.shape)
    print(mean_prior.shape)
    print(logvar_prior.shape)
    print(z.shape)
    print(y[0,:5,0])
    def loss_function(recon_x, x, mu, logvar, mu_prior=None, logvar_prior=None):
        if mu_prior is None:
            mu_prior = torch.zeros_like(mu)
        if logvar_prior is None:
            logvar_prior = torch.zeros_like(logvar)
        recon = torch.sum(  x/recon_x - torch.log(x/recon_x) - 1 ) 
        KLD = -0.5 * torch.sum(logvar - logvar_prior - torch.div((logvar.exp() + (mu - mu_prior).pow(2)), logvar_prior.exp()))
        return recon + KLD

    print(loss_function(y,x,mean,logvar,mean_prior,logvar)/6)
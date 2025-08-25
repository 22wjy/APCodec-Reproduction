import time
import torch
import torchaudio
import os
from tqdm import tqdm
import librosa
import numpy as np
import torchaudio.functional as F_audio
from exp_16k.utils import AttrDict
from exp_16k.dataset import amp_pha_specturm
from exp_16k.models import Encoder, Decoder
import json

def load_checkpoint(filepath, device):
    assert os.path.isfile(filepath)
    checkpoint_dict = torch.load(filepath, map_location=device)
    return checkpoint_dict

def calculate_rtf(config_file, audio_dir, device='cuda'):
    """
    计算 RTF（Real-Time Factor）
    :param config_file: 配置文件路径 (config.json)
    :param audio_dir: 测试音频目录 (test_input_wavs_dir)
    :param device: 计算设备 ('cuda' 或 'cpu')
    :return: RTF 值和实时倍数
    """
    # 加载配置文件
    with open(config_file) as f:
        json_config = json.loads(f.read())
    h = AttrDict(json_config)

    # 初始化模型
    encoder = Encoder(h).to(device)
    decoder = Decoder(h).to(device)

    # 加载模型权重
    state_dict_encoder = load_checkpoint(h.checkpoint_file_load_Encoder, device)
    encoder.load_state_dict(state_dict_encoder['encoder'])
    state_dict_decoder = load_checkpoint(h.checkpoint_file_load_Decoder, device)
    decoder.load_state_dict(state_dict_decoder['decoder'])

    encoder.eval()
    decoder.eval()

    # 获取测试音频文件列表
    audio_files = sorted([os.path.join(audio_dir, f) for f in os.listdir(audio_dir) if f.endswith('.wav')])

    total_generation_time = 0.0
    total_audio_duration = 0.0

    with torch.no_grad():
        for audio_path in tqdm(audio_files, desc="Processing audio files"):

            # 加载音频
            raw_wav, _ = librosa.load(audio_path, sr=h.sampling_rate, mono=True)
            raw_wav = torch.FloatTensor(raw_wav).to(device)
            logamp, pha, _, _ = amp_pha_specturm(raw_wav.unsqueeze(0), h.n_fft, h.hop_size, h.win_size)

            # 计算音频时长
            audio_duration = len(raw_wav) / h.sampling_rate  # 秒
            total_audio_duration += audio_duration

            # 测量生成时间
            if device == 'cuda':
                torch.cuda.synchronize()
            start_time = time.time()

            # 推理流程（复现 inference.py）
            latent,_,_ = encoder(logamp, pha)
            logamp_g, pha_g, _, _, y_g = decoder(latent)
            latent = latent.squeeze()
            audio = y_g.squeeze()

            if device == 'cuda':
                torch.cuda.synchronize()
            end_time = time.time()

            generation_time = end_time - start_time
            total_generation_time += generation_time

    # 计算 RTF
    rtf = total_generation_time / total_audio_duration if total_audio_duration > 0 else float('inf')
    realtime_multiple = 1.0 / rtf if rtf > 0 else float('inf')

    return rtf, realtime_multiple

def main():
    # 配置参数
    config_file = '/mnt/nvme_share/srt30/APCodec/config.json'
    audio_dir = '/mnt/nvme_share/srt30/AP-BWE-main/VCTK-Corpus-0.92/wav48/test'
    
    # 设置设备
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    torch.manual_seed(1234)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(1234)

    # 计算 RTF
    rtf, realtime_multiple = calculate_rtf(config_file, audio_dir, device)
    print(f"RTF: {rtf:.4f}, Realtime Multiple: {realtime_multiple:.2f}x")

if __name__ == '__main__':
    main()
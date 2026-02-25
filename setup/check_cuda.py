import torch

def main():
    cuda_available = torch.cuda.is_available()
    print(cuda_available)

if __name__ == "__main__":
    main()
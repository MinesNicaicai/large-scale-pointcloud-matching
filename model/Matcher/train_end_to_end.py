from model.Matcher.superglue import SuperGlue
from model.Matcher.matcher_dataset import *
from model.Descriptor.descnet import DgcnnModel
from model.Transform.rtnet import *
import argparse
import os
from torch.utils.data import DataLoader
import torch.optim as optim
import visdom
from tqdm import tqdm


parser = argparse.ArgumentParser(description='MatcherTrain')
parser.add_argument('--dataset_dir', type=str, default="/media/admini/My_data/matcher_database/00", help='dataset_dir')
parser.add_argument('--checkpoints_dir', type=str,
                    default="/media/admini/My_data/matcher_database/checkpoints", help='checkpoints_dir')
parser.add_argument('--add_random_rotation', type=bool, default=True, help='add_random_rotation')
parser.add_argument('--load_descriptor_net', type=bool, default=True, help='load_descriptor_net')
parser.add_argument('--load_superglue', type=bool, default=True, help='load_superglue')
parser.add_argument('--learning_rate', type=float, default=1e-3, help='learning_rate')
parser.add_argument('--batch_size', type=int, default=1, help='batch_size')
parser.add_argument('--translation_loss_weight', type=float, default=0.0000010, help='translation_loss_weight')
parser.add_argument('--rotation_loss_weight', type=float, default=0.00000100, help='rotation_loss_weight')
parser.add_argument('--match_loss_weight', type=float, default=1, help='match_loss_weight')

args = parser.parse_args()


def compute_metrics(matches0, matches1, match_matrix_ground_truth):
    matches0 = np.array(matches0.cpu()).reshape(-1).squeeze() # M
    matches1 = np.array(matches1.cpu()).reshape(-1).squeeze() # N
    match_matrix_ground_truth = np.array(match_matrix_ground_truth.cpu()).squeeze()  # M*N

    matches0_idx_tuple = (np.arange(len(matches0)), matches0)
    matches1_idx_tuple = (np.arange(len(matches1)), matches1)

    matches0_precision_idx_tuple = (np.arange(len(matches0))[matches0>0], matches0[matches0>0])
    matches1_precision_idx_tuple = (np.arange(len(matches1))[matches1>0], matches1[matches1>0])

    matches0_recall_idx_tuple = (np.arange(len(matches0))[match_matrix_ground_truth[:-1, -1] == 0],
                                 matches0[match_matrix_ground_truth[:-1, -1] == 0])
    matches1_recall_idx_tuple = (np.arange(len(matches1))[match_matrix_ground_truth[-1, :-1] == 0],
                                 matches1[match_matrix_ground_truth[-1, :-1] == 0])

    # match_0_acc = match_matrix_ground_truth[:-1, :][matches0_precision_idx_tuple].mean()
    # match_1_acc = match_matrix_ground_truth.T[:-1, :][matches1_precision_idx_tuple].mean()

    metrics = {
        "matches0_acc": match_matrix_ground_truth[:-1, :][matches0_idx_tuple].mean(),
        "matches1_acc": match_matrix_ground_truth.T[:-1, :][matches1_idx_tuple].mean(),
        "matches0_precision": match_matrix_ground_truth[:-1, :][matches0_precision_idx_tuple].mean(),
        "matches1_precision": match_matrix_ground_truth.T[:-1, :][matches1_precision_idx_tuple].mean(),
        "matches0_recall": match_matrix_ground_truth[:-1, :][matches0_recall_idx_tuple].mean(),
        "matches1_recall": match_matrix_ground_truth.T[:-1, :][matches1_recall_idx_tuple].mean()
    }
    return metrics


def train():
    h5_filename = os.path.join(args.dataset_dir, "submap_segments.h5")
    correspondences_filename = os.path.join(args.dataset_dir, "correspondences.txt")
    matcher_dataset = MatcherDataset(h5_filename, correspondences_filename, mode='train')

    train_loader = DataLoader(matcher_dataset, batch_size=1, shuffle=True)
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # descnet is trained together
    descriptor_dim = 256
    descnet = DgcnnModel(k=5, feature_dims=[64, 128, 256], emb_dims=[512, 256], output_classes=descriptor_dim)
    descnet_ckp_filename = "descriptor-256-dgcnn-e2e-kitti00.pth"

    if args.load_descriptor_net:
        dgcnn_model_checkpoint = torch.load(os.path.join(args.checkpoints_dir, descnet_ckp_filename),
                                            map_location=lambda storage, loc: storage)
        descnet.load_state_dict(dgcnn_model_checkpoint)
        print("Loaded model checkpoints from \'{}\'.".format(
            os.path.join(args.checkpoints_dir, descnet_ckp_filename)))
    descnet.to(dev)

    # Superglue can be trained from scratch
    super_glue_config = {
        'descriptor_dim': descriptor_dim,
        'weights': '',
        'keypoint_encoder': [32, 64, 128, 256],
        'GNN_layers': ['self', 'cross'] * 6,
        'sinkhorn_iterations': 150,
        'match_threshold': 0.1,
    }
    superglue = SuperGlue(super_glue_config)
    superglue = superglue.to(dev)
    superglue_ckp_filename = "Superglue-256-dgcnn-e2e-kitti00.pth"
    if args.load_superglue:
        superglue.load_state_dict(torch.load(os.path.join(args.checkpoints_dir, superglue_ckp_filename), map_location=dev))

    # train Superglue and descnet

    opt = optim.Adam(list(descnet.parameters()) + list(superglue.parameters()), lr=1e-4, weight_decay=2e-6)

    num_epochs = 5

    # scheduler = optim.lr_scheduler.CosineAnnealingLR(opt, num_epochs, eta_min=0.001)
    # scheduler.step()
    # descnet.eval()
    superglue.train()


    viz = visdom.Visdom()
    win_loss = viz.scatter(X=np.asarray([[0, 0]]))
    win_precision = viz.scatter(X=np.asarray([[0, 0]]))
    win_recall = viz.scatter(X=np.asarray([[0, 0]]))

    num_losses = 0
    with tqdm(train_loader) as tq:
        item_idx = 0
        for centers_A, centers_B, segments_A, segments_B, match_mask_ground_truth, T_A_B in tq:
            # segments_A = [segment.to(dev) for segment in segments_A]
            # segments_B = [segment.to(dev) for segment in segments_B]
            # descriptors_A = torch.Tensor.new_empty(1, 256, len(segments_A), device=dev)
            # descriptors_B = torch.Tensor.new_empty(1, 256, len(segments_B), device=dev)

            # Get descriptors from descnet
            descriptors_A = []
            descriptors_B = []

            for segment in segments_A:
                # descriptors_A.append(model(segment.to(dev), dev))
                descriptors_A.append(descnet(segment.to(dev)))
            for segment in segments_B:
                # descriptors_B.append(model(segment.to(dev), dev))
                descriptors_B.append(descnet(segment.to(dev)))
            descriptors_A = torch.cat(descriptors_A, dim=0).transpose(0, 1).reshape(1, descriptor_dim, -1)
            descriptors_B = torch.cat(descriptors_B, dim=0).transpose(0, 1).reshape(1, descriptor_dim, -1)
            data = {
                'descriptors0': descriptors_A,
                'descriptors1': descriptors_B,
                'keypoints0': centers_A.to(dev),
                'keypoints1': centers_B.to(dev),
            }


            # for i in range(len(segments_A)):
            #     descriptors_A[0, :, i] = model(segments_A[i], dev)
            # for i in range(len(segments_B)):
            #     descriptors_B.append(model(segment, dev))

            # Train Superglue
            match_output = superglue(data)
            match_loss = -match_output['scores'] * match_mask_ground_truth.to(dev)
            rot_A_B, trans_A_B = torch_icp(centers_A.to(dev)[:,:,:3], centers_B.to(dev)[:,:,:3], match_output['scores'][:,:-1,:-1])

            rot_A_B = rot_A_B.squeeze()
            trans_A_B = trans_A_B.squeeze()

            T_A_B = T_A_B.to(dev)
            T_B_A_gt = T_A_B.squeeze().inverse()
            rot_B_A_gt = T_B_A_gt[:3, :3]
            trans_B_A_gt = T_B_A_gt[:3, 3:]

            delta_rot = rot_A_B @ rot_B_A_gt
            delta_trans = (rot_A_B @ trans_B_A_gt).squeeze() + trans_A_B

            rt_loss = args.rotation_loss_weight * torch.acos(0.5*(torch.trace(delta_rot)-1)) \
                      + args.translation_loss_weight * torch.sqrt(delta_trans @ delta_trans)

            match_loss = match_loss.sum()
            loss = args.match_loss_weight * match_loss + rt_loss

            if num_losses == 0:
                sum_loss = loss
            elif num_losses < args.batch_size:
                sum_loss += loss
            num_losses += 1

            if num_losses == args.batch_size:
                loss = sum_loss / args.batch_size
                loss.backward()
                opt.step()
                opt.zero_grad()
                num_losses = 0


            print("loss: {}".format(loss.item()))

            # TODO: evaluate accuracy
            metrics = compute_metrics(match_output['matches0'], match_output['matches1'], match_mask_ground_truth)
            print("accuracies: matches0({}), matches1({})".format(metrics['matches0_acc'], metrics['matches1_acc']))
            print("precisions: matches0({}), matches1({})".format(metrics['matches0_precision'], metrics['matches1_precision']))
            print("recalls: matches0({}), matches1({})".format(metrics['matches0_recall'], metrics['matches1_recall']))

            viz.scatter(X=np.array([[item_idx, float(loss)]]),
                        name="train-loss",
                        win=win_loss,
                        update="append")
            viz.scatter(X=np.array([[item_idx, float(metrics['matches0_precision'])]]),
                        name="train-precision",
                        win=win_precision,
                        update="append")
            viz.scatter(X=np.array([[item_idx, float(metrics['matches0_recall'])]]),
                        name="train-recall",
                        win=win_recall,
                        update="append")

            item_idx += 1
            if item_idx % 200 == 0:
                torch.save(descnet.state_dict(), os.path.join(args.checkpoints_dir, descnet_ckp_filename))
                torch.save(superglue.state_dict(), os.path.join(args.checkpoints_dir, superglue_ckp_filename))
                print("descnet model saved in {}".format(os.path.join(args.checkpoints_dir, descnet_ckp_filename)))
                print("Superglue model saved in {}".format(os.path.join(args.checkpoints_dir, superglue_ckp_filename)))


if __name__ == '__main__':
    train()
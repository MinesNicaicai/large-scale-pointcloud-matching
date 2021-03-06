#include <iostream>
#include <vector>
#include <set>
#include <algorithm>

#include <pcl/io/pcd_io.h>
#include <pcl/common/common.h>
#include <pcl/filters/voxel_grid.h>
#include <pcl/filters/approximate_voxel_grid.h>

// 1. read file
// 2. histogram of xy plane
// 3. select the top k grids with most points

#if 0
template<typename T>
class Grid : public std::vector<std::vector<T>> {
public:
    Grid(std::size_t m, std::size_t n) : m_(m), n_(n), std::vector<std::vector<T>>(m, std::vector<T>(n))
    {}

    Grid(std::size_t m, std::size_t n, T val) : m_(m), n_(n), std::vector<std::vector<T>>(m, std::vector<T>(n, val))
    {}

    T at(int x, int y)
    {
        return this[x][y];
    }
private:
    std::size_t m_;
    std::size_t n_;
};
#endif 


template<typename T>
class Grid : public std::vector<T> {
public:
    Grid(std::size_t m, std::size_t n) : m_(m), n_(n)
    {
        this->resize(m_ * n_);
    }

    Grid(std::size_t m, std::size_t n, T val) : m_(m), n_(n)
    {
        this->resize(m_ * n_, val);
    }

    T& at(std::size_t x, std::size_t y)
    {
        return (*this)[x * n_ + y];
    }

    // virtual void sort()
    // {
    //     std::sort(this->begin(), this->end());
    // }

private:
    std::size_t m_;
    std::size_t n_;
};

template<typename PointT>
class DataBin : public std::vector<PointT>{

public:
    int get_height_distribution(float resolution)
    {
        std::set<int> height_indices;
        for (const auto& point : *this) {
            height_indices.insert(int (point.z / resolution));
        }
        
        return height_indices.size();
    }

};

// template<typename PointT>
// void Grid<DataBin<PointT>>::sort()
// {
//     std::sort(this->begin(), this->end(), [](auto bin_x, auto bin_y){
//         return bin_x.get_height_distribution < bin_y.get_height_distribution;
//     });
// }

template<typename PointT>
Grid<int> make_grid_with_count(const pcl::PointCloud<PointT>& cloud, float scale, float resolution)
{
    // 1. calculate the center
    pcl::PointXYZ center(0,0,0);
    for (const auto& point : cloud->points) {
        center.x += point.x;
        center.y += point.y;
        center.z += point.z;
    }
    center.x /= cloud->size();
    center.y /= cloud->size();
    center.z /= cloud->size();

    // 2. make a grid
    int grid_size = int(scale / resolution);
    Grid<int> grid(grid_size, grid_size, 0);

    std::cout << "grid initialization success\n";

    for (const auto& point : cloud->points) {
        int x_index = (point.x - center.x + scale / 2) / resolution;
        int y_index = (point.y - center.y + scale / 2) / resolution;
        // std::cout << "(xid, yid) = (" << x_index << "," << y_index << ")\n";
        if (0 <=x_index && x_index < grid_size && 0 <= y_index && y_index < grid_size) {
            // std::cout << grid.at(x_index, y_index) << std::endl;
            ++grid.at(x_index, y_index);
        }
    }

    return grid;
}


template<typename PointT>
Grid<std::vector<std::size_t>> make_grid_with_indices(const pcl::PointCloud<PointT>& cloud, float scale, float resolution)
{
    // 1. calculate the center
    pcl::PointXYZ center(0,0,0);
    for (const auto& point : cloud.points) {
        center.x += point.x;
        center.y += point.y;
        center.z += point.z;
    }
    center.x /= cloud.size();
    center.y /= cloud.size();
    center.z /= cloud.size();

    // 2. make a grid
    int grid_size = int(scale / resolution);
    Grid<std::vector<std::size_t>> grid(grid_size, grid_size);
    std::cout << "grid initialization success\n";

    for (std::size_t i = 0; i < cloud.size(); ++i) {
        std::size_t x_index = (cloud.points[i].x - center.x + scale / 2) / resolution;
        std::size_t y_index = (cloud.points[i].y - center.y + scale / 2) / resolution;
        if (0 <= x_index && x_index < grid_size && 0 <= y_index && y_index < grid_size) {
            grid.at(x_index, y_index).emplace_back(i);
        }
    }

    return grid;
}

template<typename PointT>
Grid<DataBin<PointT>> make_grid_with_databins(const pcl::PointCloud<PointT>& cloud,
        float scale, float resolution)
{
    // 1. calculate the center
    pcl::PointXYZ center(0,0,0);
    for (const auto& point : cloud.points) {
        center.x += point.x;
        center.y += point.y;
        center.z += point.z;
    }
    center.x /= cloud.size();
    center.y /= cloud.size();
    center.z /= cloud.size();

    // 2. make a grid
    int grid_size = int(scale / resolution);
    Grid<DataBin<PointT>> grid(grid_size, grid_size);
    std::cout << "grid initialization success\n";

    for (std::size_t i = 0; i < cloud.size(); ++i) {
        std::size_t x_index = (cloud.points[i].x - center.x + scale / 2) / resolution;
        std::size_t y_index = (cloud.points[i].y - center.y + scale / 2) / resolution;
        if (0 <= x_index && x_index < grid_size && 0 <= y_index && y_index < grid_size) {
            grid.at(x_index, y_index).emplace_back(cloud.points[i]);
        }
    }

    return grid;
}


int bird_view_poi(int argc, char** argv)
{
    if (argc != 2) {
        std::cout << "usage: ./bird_view_poi point_cloud.pcd" << std::endl;

        return -1;
    }

    // 1. read file
    // pcl::PCDReader reader;
    // reader.read (argv[1], *cloud_in);

    pcl::PointCloud<pcl::PointXYZI>::Ptr cloud_in(new pcl::PointCloud<pcl::PointXYZI>);
        pcl::PointCloud<pcl::PointXYZRGB>::Ptr cloud_out(new pcl::PointCloud<pcl::PointXYZRGB>);
    if ( pcl::io::loadPCDFile <pcl::PointXYZI> (argv[1], *cloud_in) == -1 )
    {
        std::cout << "Cloud reading failed." << std::endl;
        return (-1);
    }

    std::cout << "cloud_in has: " << cloud_in->points.size () << " data points." << std::endl;

    // Create the filtering object: downsample the dataset using a leaf size of 1cm
    pcl::ApproximateVoxelGrid<pcl::PointXYZI> vg;
    // pcl::PointCloud<pcl::PointXYZ>::Ptr cloud_filtered (new pcl::PointCloud<pcl::PointXYZ>);
    vg.setInputCloud (cloud_in);
    vg.setLeafSize (0.1f, 0.1f, 0.1f);
    // vg.filter (*cloud_in);

    // 2. histogram of xy plane
    const float scale = 100.f;
    const float resolution = 0.4f;

#if 0
    {
        auto grid = make_grid_with_count(cloud_in, scale, resolution);
        grid.sort();
        int k = 400;
        for (auto iter = grid.end(); grid.end() - iter < k;) {
            std::cout << *(--iter) << std::endl;
        }
    }
#endif

#if 0
    {
        pcl::copyPointCloud(*cloud_in, *cloud_out);
        auto grid = make_grid_with_indices(*cloud_in, scale, resolution);
        std::sort(grid.begin(), grid.end(), [](auto square_x, auto square_y){
            return square_x.size() < square_y.size();
        });

        int k = 100;
        for (auto iter = std::prev(grid.end()); iter >= grid.end() - k; --iter) {
            std::cout << iter->size() << std::endl;
            int r = rand() % 192 + 64;
            int g = rand() % 192 + 64;
            int b = rand() % 192 + 64;
            for (const auto& index : (*iter)) {
                cloud_out->points[index].r = r;
                cloud_out->points[index].g = g;
                cloud_out->points[index].b = b;
            }
        }
        
    }
#endif

    {
        auto grid = make_grid_with_databins(*cloud_in, scale, resolution);
        const float height_resolution = 0.2;
        std::sort(grid.begin(), grid.end(), [height_resolution](auto& x, auto& y){
            return x.get_height_distribution(height_resolution) < y.get_height_distribution(height_resolution);
        });

        int k = 300;
        for (auto iter = std::prev(grid.end()); iter >= grid.end() - k; --iter) {
            // std::cout << iter->size() << std::endl;
            int r = rand() % 192 + 64;
            int g = rand() % 192 + 64;
            int b = rand() % 192 + 64;
            for (const auto& p : *iter) {
                pcl::PointXYZRGB point(r, g, b);
                point.x = p.x;
                point.y = p.y;
                point.z = p.z;
                cloud_out->points.emplace_back(point);
            }
        }
        for (auto iter = std::prev(grid.end() - k); iter >= grid.begin(); --iter) {
            for (const auto& p : *iter) {
                pcl::PointXYZRGB point(10, 10, 10);
                point.x = p.x;
                point.y = p.y;
                point.z = p.z;
                cloud_out->points.emplace_back(point);
            }
        }
        
    }
    
    cloud_out->width = 1;
    cloud_out->height = cloud_out->size();
    if ( pcl::io::savePCDFile <pcl::PointXYZRGB> ("bird_view_poi_output.pcd", *cloud_out) == -1 )
    {
        std::cout << "Cloud writing failed." << std::endl;
        return (-1);
    }

    return 0;
}


int main(int argc, char** argv)
{
    return bird_view_poi(argc, argv);
}